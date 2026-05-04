import os
import json
import telebot
from flask import Flask, request

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

ROUTE_FILE = "routes.json"
recent_relays = set()

# =========================
# STORAGE
# =========================
def load_routes():
    try:
        with open(ROUTE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_routes(routes):
    with open(ROUTE_FILE, "w", encoding="utf-8") as f:
        json.dump(routes, f, indent=4)

ROUTES = load_routes()

# =========================
# ADMIN CHECK
# =========================
def is_admin(message):
    return True
# =========================
# START
# =========================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    if not is_admin(message):
        return
    bot.reply_to(
        message,
        "✅ RelayMaster Bot Online\\n\\n"
        "/id - Get current Chat ID and Topic ID\\n"
        "/addroute sourcechat sourcetopic destchat desttopic\\n"
        "/routes - Show all active routes\\n"
        "/delroute number\\n"
        "/clearall - Delete all routes"
    )

# =========================
# GET IDS
# =========================
@bot.message_handler(commands=['id'])
def id_cmd(message):
    if not is_admin(message):
        return
    chat_id = message.chat.id
    topic_id = getattr(message, "message_thread_id", None)
    bot.reply_to(
        message,
        f"🆔 CHAT ID: <code>{chat_id}</code>\\n🧵 TOPIC ID: <code>{topic_id}</code>"
    )

# =========================
# ADD ROUTE
# =========================
@bot.message_handler(commands=['addroute'])
def add_route(message):
    global ROUTES
    if not is_admin(message):
        return

    try:
        parts = message.text.split()

        source_chat = int(parts[1])
        source_topic = None if parts[2].lower() == "none" else int(parts[2])
        dest_chat = int(parts[3])
        dest_topic = None if parts[4].lower() == "none" else int(parts[4])

        new_route = {
            "source_chat": source_chat,
            "source_topic": source_topic,
            "dest_chat": dest_chat,
            "dest_topic": dest_topic
        }

        ROUTES.append(new_route)
        save_routes(ROUTES)
        bot.reply_to(message, "✅ Route added successfully.")

    except Exception as e:
        bot.reply_to(message, f"❌ Usage:\\n/addroute sourcechat sourcetopic destchat desttopic\\n\\nError: {e}")

# =========================
# SHOW ROUTES
# =========================
@bot.message_handler(commands=['routes'])
def show_routes(message):
    if not is_admin(message):
        return

    if not ROUTES:
        bot.reply_to(message, "No routes configured.")
        return

    txt = "📡 ACTIVE ROUTES:\\n\\n"
    for i, r in enumerate(ROUTES, start=1):
        txt += (
            f"{i}. FROM: {r['source_chat']} | Topic: {r['source_topic']}\\n"
            f"   TO: {r['dest_chat']} | Topic: {r['dest_topic']}\\n\\n"
        )
    bot.reply_to(message, txt)

# =========================
# DELETE ROUTE
# =========================
@bot.message_handler(commands=['delroute'])
def del_route(message):
    global ROUTES
    if not is_admin(message):
        return

    try:
        num = int(message.text.split()[1]) - 1
        if 0 <= num < len(ROUTES):
            ROUTES.pop(num)
            save_routes(ROUTES)
            bot.reply_to(message, "🗑 Route deleted.")
        else:
            bot.reply_to(message, "❌ Invalid route number.")
    except:
        bot.reply_to(message, "Usage: /delroute number")

# =========================
# CLEAR ALL
# =========================
@bot.message_handler(commands=['clearall'])
def clear_all(message):
    global ROUTES
    if not is_admin(message):
        return

    ROUTES = []
    save_routes(ROUTES)
    bot.reply_to(message, "🗑 All routes cleared.")

# =========================
# RELAY FUNCTION
# =========================
def process_relay(message):
    global ROUTES, recent_relays

    try:
        src_chat = message.chat.id
        src_topic = getattr(message, "message_thread_id", None)

        signature = f"{src_chat}:{src_topic}:{message.message_id}"
        if signature in recent_relays:
            return

        for route in ROUTES:
            if src_chat != route["source_chat"]:
                continue

            if route["source_topic"] is not None and src_topic != route["source_topic"]:
                continue

            try:
                if route["dest_topic"] is not None:
                    sent = bot.copy_message(
                        chat_id=route["dest_chat"],
                        from_chat_id=src_chat,
                        message_id=message.message_id,
                        message_thread_id=route["dest_topic"]
                    )
                else:
                    sent = bot.copy_message(
                        chat_id=route["dest_chat"],
                        from_chat_id=src_chat,
                        message_id=message.message_id
                    )

                recent_relays.add(f"{route['dest_chat']}:{route['dest_topic']}:{sent.message_id}")

            except Exception as e:
                print("Copy error:", e)

        if len(recent_relays) > 500:
            recent_relays = set(list(recent_relays)[-200:])

    except Exception as e:
        print("Relay engine error:", e)

# =========================
# GROUP/TOPIC MESSAGES
# =========================
@bot.message_handler(func=lambda m: True, content_types=[
    'text', 'photo', 'video', 'document', 'audio', 'voice', 'sticker', 'animation'
])
def universal_handler(message):
    process_relay(message)

# =========================
# CHANNEL POSTS
# =========================
@bot.channel_post_handler(func=lambda m: True, content_types=[
    'text', 'photo', 'video', 'document', 'audio', 'voice', 'sticker', 'animation'
])
def channel_handler(message):
    process_relay(message)

# =========================
# WEBHOOK
# =========================
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "ok", 200

@app.route("/")
def home():
    return "RelayMaster Running"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
