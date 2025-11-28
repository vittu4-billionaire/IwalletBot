import os
from flask import Flask, request, jsonify
import requests
from dotenv import load_dotenv        # <-- add this

# Load .env file
load_dotenv()                         # <-- and this

app = Flask(__name__)

# === CONFIG – fill these with your real values ===
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")  # from Meta (long-lived token)
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")  # from "API Setup" screen
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "my_secret_token")  # same as in dashboard
FORWARD_TO_NUMBER = os.environ.get("FORWARD_TO_NUMBER")  # the other WhatsApp number (with country code, no +)

# Our 3 questions (UPDATED)
QUESTIONS = [
    (
        "Hello,\n"
        "Happy Folks!\n\n"
        "1) Welcome to I WALLET FIN TECHNOLOGY.\n"
        "We’re delighted to have you with us!\n\n"
        "If you have any questions or need assistance, feel free to reach out.\n"
        "Our support team is always here to help and will assist you as soon as possible.\n\n"
        "To proceed further, please provide your Name and Mobile Number."
    ),
    (
        "2) May I know what service you need today?\n"
        "- Swipe\n"
        "- Bill Payment"
    ),
    "3) Which city are you currently in?"
]

# Simple in-memory conversation store: { user_number: {"step": int, "answers": []} }
conversations = {}

def send_whatsapp_text(to, text):
    """
    Send a text message using WhatsApp Cloud API.
    """
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    r = requests.post(url, headers=headers, json=data)
    print("Send message status:", r.status_code, r.text)

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """
    Meta verification endpoint – called once when you set the webhook.
    """
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    else:
        return "Forbidden", 403

@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.get_json()
    print("Incoming:", data)

    # Basic safety check
    if data.get("object") != "whatsapp_business_account":
        return "Ignored", 200

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])
            for message in messages:
                if message.get("type") != "text":
                    continue

                from_number = message["from"]         # e.g. "9198xxxxxx"
                text = message["text"]["body"].strip()

                handle_user_message(from_number, text)

    return "OK", 200

def handle_user_message(user_number, text):
    """
    Conversation logic for one user.
    """
    state = conversations.get(user_number, {"step": 0, "answers": []})
    step = state["step"]
    answers = state["answers"]

    if step == 0 and not answers:
        # Start → ask Q1 (welcome + ask Name & Mobile)
        send_whatsapp_text(user_number, QUESTIONS[0])
        state["step"] = 1
    elif step == 1:
        # User replied with Name & Mobile
        answers.append(text)
        send_whatsapp_text(user_number, QUESTIONS[1])
        state["step"] = 2
    elif step == 2:
        # User replied with service needed
        answers.append(text)
        send_whatsapp_text(user_number, QUESTIONS[2])
        state["step"] = 3
    elif step == 3:
        # User replied with city
        answers.append(text)

        # ✅ Updated final message
        send_whatsapp_text(
            user_number,
            "Thank you! We have received your details. ✅\n\n"
            "Our staff will reach out to you shortly.\n"
            "Business Hours: 10:30 AM to 7:30 PM, Monday To Saturday\n"
            "For emergencies, please contact: 98941 45444"
        )

        # Summary to forward internally
        summary = (
            f"New lead from WhatsApp:\n"
            f"WhatsApp Number: {user_number}\n\n"
            f"1) Name & Mobile (as provided):\n{answers[0]}\n\n"
            f"2) Service needed today:\n{answers[1]}\n\n"
            f"3) City:\n{answers[2]}"
        )

        if FORWARD_TO_NUMBER:
            send_whatsapp_text(FORWARD_TO_NUMBER, summary)

        conversations.pop(user_number, None)
        return
    else:
        # Reset if something goes off
        send_whatsapp_text(user_number, "Let's start again.")
        send_whatsapp_text(user_number, QUESTIONS[0])
        state = {"step": 1, "answers": []}

    conversations[user_number] = state

if __name__ == "__main__":
    app.run(port=5000, debug=True)
