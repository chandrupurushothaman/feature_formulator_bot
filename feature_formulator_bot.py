import os
from threading import Thread
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from chatterbot import ChatBot
from chatterbot.trainers import ChatterBotCorpusTrainer

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")
REQUIREMENT_CHANNEL_ID = os.environ.get("REQUIREMENT_CHANNEL_ID", "C09LE8XGHPZ")

app = App(token=SLACK_BOT_TOKEN)

chatbot = ChatBot(
    "FeatureFormulator",
    storage_adapter="chatterbot.storage.SQLStorageAdapter",
    database_uri="sqlite:///database.sqlite3",
    logic_adapters=[
        {
            "import_path": "chatterbot.logic.BestMatch",
            "default_response": (
                "I'm sorry, I'm not sure how to respond to that. "
                "I am designed to help you formulate feature requirements. "
                "To get started, you can say 'new feature' or 'I have an idea'."
            ),
            "maximum_similarity_threshold": 0.90
        }
    ],
)

trainer = ChatterBotCorpusTrainer(chatbot)
trainer.train("chatterbot.corpus.english")
print("🤖 ChatterBot has been trained with the full English corpus and is ready.")

user_requirement_flows = {}

REQUIREMENT_TEMPLATE = """
*🚀 New Requirement Submitted*

*Submitted By:* <@{user_id}>
*Priority:* {priority}
*Target Deadline:* {deadline}

*Title:*
{title}

*User Story:*
As a {user_type}, I want {action}, so that {benefit}.

*Acceptance Criteria:*
{criteria}

*Key Stakeholders:*
{stakeholders}

*Dependencies:*
{dependencies}
"""


def start_requirement_flow(user_id, say):
    """Initialize a new feature requirement flow."""
    user_requirement_flows[user_id] = {"step": "awaiting_title", "data": {}}
    say("Excellent! I can help formalize that idea. First, what is the short, descriptive title for this new feature or enhancement?")
    say("_For example: 'Dashboard CSV Export Button'_")


def continue_requirement_flow(user_id, message_text, say):
    """Guides the user through the data collection steps."""
    flow = user_requirement_flows.get(user_id)
    if not flow:
        return

    current_step = flow["step"]
    message_text = message_text.strip()

    if current_step == "awaiting_title":
        flow["data"]["title"] = message_text
        flow["step"] = "awaiting_user_story"
        flow["sub_step"] = "user_type"
        say("Got it. Now, please describe the User Story. I'll break it down for you.")
        say("First, who is the user? (e.g., 'Project Manager', 'Marketing Analyst')")

    elif current_step == "awaiting_user_story":
        sub_step = flow.get("sub_step")

        if sub_step == "user_type":
            flow["data"]["user_type"] = message_text
            flow["sub_step"] = "action"
            say(f"Okay, the user is a *{message_text}*. Next, what do they want to do?")
            say("_For example: 'to download a CSV of the project data'_")

        elif sub_step == "action":
            flow["data"]["action"] = message_text
            flow["sub_step"] = "benefit"
            say("Perfect. And finally, what is the benefit or goal they achieve by doing this?")
            say("_For example: 'so that I can perform offline analysis in Excel'_")

        elif sub_step == "benefit":
            flow["data"]["benefit"] = message_text
            flow["step"] = "awaiting_criteria"
            flow.pop("sub_step", None)
            say("Great user story! Now, please list the Acceptance Criteria.")
            say("_Example:_\n• The button is on the main dashboard.\n• The downloaded file is named 'export.csv'_")

    elif current_step == "awaiting_criteria":
        flow["data"]["criteria"] = message_text
        flow["step"] = "awaiting_stakeholders"
        say("Thank you. Now, please @mention any key stakeholders. If there are none, just type `None`.")

    elif current_step == "awaiting_stakeholders":
        flow["data"]["stakeholders"] = message_text
        flow["step"] = "awaiting_dependencies"
        say("Got it. Are there any dependencies on other teams or services? If not, type `None`.")

    elif current_step == "awaiting_dependencies":
        flow["data"]["dependencies"] = message_text
        flow["step"] = "awaiting_deadline"
        say("Almost done! Is there a target deadline or release date? If flexible, type `None`.")

    elif current_step == "awaiting_deadline":
        flow["data"]["deadline"] = message_text
        flow["step"] = "awaiting_priority"
        say(blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "That's everything I need. What is the priority of this request?"}
            },
            {
                "type": "actions",
                "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "Low"}, "value": "Low", "action_id": "priority_low"},
                    {"type": "button", "text": {"type": "plain_text", "text": "Medium"}, "value": "Medium", "action_id": "priority_medium"},
                    {"type": "button", "text": {"type": "plain_text", "text": "High"}, "style": "primary", "value": "High", "action_id": "priority_high"},
                    {"type": "button", "text": {"type": "plain_text", "text": "Critical"}, "style": "danger", "value": "Critical", "action_id": "priority_critical"}
                ]
            }
        ])


def post_requirement_to_channel(client, user_id, requirement_data):
    try:
        requirement_data["user_id"] = user_id
        formatted_requirement = REQUIREMENT_TEMPLATE.format(**requirement_data)

        client.chat_postMessage(
            channel=REQUIREMENT_CHANNEL_ID,
            text="New Requirement Submitted",
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": formatted_requirement}}]
        )
        print(f"✅ Successfully posted requirement for user {user_id} to channel {REQUIREMENT_CHANNEL_ID}")
    except Exception as e:
        print(f"❌ Error posting requirement: {e}")
        client.chat_postMessage(channel=user_id, text="I ran into an error posting to the channel. Please ensure I'm a member of it.")


@app.message("")
def handle_message(message, say):
    user_id = message["user"]
    message_text = message["text"].strip()
    Thread(target=process_message_logic, args=(user_id, message_text, say)).start()


def process_message_logic(user_id, message_text, say):
    if user_id in user_requirement_flows:
        if message_text.lower() == "cancel":
            del user_requirement_flows[user_id]
            say("✅ I've cancelled your current requirement flow. You can start a new one anytime.")
        else:
            continue_requirement_flow(user_id, message_text, say)
        return

    requirement_keywords = ["feature", "idea", "requirement", "enhancement", "we should", "implement", "new feature"]
    if any(keyword in message_text.lower() for keyword in requirement_keywords):
        start_requirement_flow(user_id, say)
    else:
        bot_response = str(chatbot.get_response(message_text))
        say(bot_response)


def handle_priority_selection(ack, body, say, client, priority):
    ack()
    user_id = body["user"]["id"]
    flow = user_requirement_flows.get(user_id)

    if not flow or flow["step"] != "awaiting_priority":
        say("It looks like we're out of sync. Please start a new requirement if you need to.")
        return

    flow["data"]["priority"] = priority
    flow["step"] = "awaiting_confirmation"

    preview_data = flow["data"].copy()
    preview_data["user_id"] = user_id
    summary_text = REQUIREMENT_TEMPLATE.format(**preview_data)

    say(blocks=[
        {"type": "section", "text": {"type": "mrkdwn", "text": "Great! Please review the requirement below before I post it."}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": summary_text}},
        {"type": "divider"},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "✅ Confirm & Post"}, "style": "primary", "value": "confirm_post", "action_id": "action_confirm_post"},
            {"type": "button", "text": {"type": "plain_text", "text": "❌ Cancel"}, "style": "danger", "value": "cancel_post", "action_id": "action_cancel_post"}
        ]}
    ])


@app.action("priority_low")
@app.action("priority_medium")
@app.action("priority_high")
@app.action("priority_critical")
def handle_priority_actions(ack, body, say, client):
    priority_level = body["actions"][0]["value"]
    handle_priority_selection(ack, body, say, client, priority_level)


@app.action("action_confirm_post")
def handle_confirm_post_action(ack, body, say, client):
    ack()
    user_id = body["user"]["id"]
    flow = user_requirement_flows.get(user_id)

    if not flow or flow["step"] != "awaiting_confirmation":
        say("It looks like we're out of sync or this has already been posted.")
        return

    say("✅ Thank you! Posting this requirement to the backlog channel now...")
    Thread(target=post_requirement_to_channel, args=(client, user_id, flow["data"])).start()
    del user_requirement_flows[user_id]


@app.action("action_cancel_post")
def handle_cancel_post_action(ack, body, say):
    ack()
    user_id = body["user"]["id"]
    if user_id in user_requirement_flows:
        del user_requirement_flows[user_id]
    say("❌ Okay, I've cancelled the submission. Feel free to start over.")


if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    try:
        print("🤖 Feature Formulator Bot is starting in Socket Mode...")
        handler.start()
    except (KeyboardInterrupt, SystemExit):
        print("🧹 Bot shutting down...")
    finally:
        user_requirement_flows.clear()
        print("✅ Shutdown complete.")
