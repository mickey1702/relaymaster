import os
import json
import telebot
import traceback
import threading
import time
from queue import Queue
from flask import Flask, request
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = str(os.getenv("ADMIN_ID", "0")).strip()

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=False)
app = Flask(__name__)

# ================================
# FILES
# ================================
ROUTE_FILE = "routes.json"
REGISTRY_FILE = "vault_registry.json"

recent_relays = set()
route_queues = {}
route_workers = {}

# ================================
# FIXED DESTINATIONS
# ================================
BACKUP_CHAT_ID = -1003784514496
BACKUP_TOPIC_ID = 841

VAULT_CHAT_ID = -1003967178737
ADMIN_LOG_TOPIC_ID = 1101

# VAULT INSTITUTE TOPICS
VAULT_TOPICS = {
    "clinicalguruji": 343,
    "mist": 6,
    "bellum": 7,
    "pw": 9
}

# ================================
# LOAD / SAVE ROUTES
# ================================
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

# ================================
# LOAD / SAVE REGISTRY DATABASE
# ================================
def load_registry():
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_registry(data):
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

VAULT_REGISTRY = load_registry()

# ================================
# ADMIN CHECK
# ================================
def is_admin(message):
    return True

# ================================
# ROUTE KEY
# ================================
def get_route_key(route):
    return f"{route['source_chat']}_{route['source_topic']}_{route['dest_chat']}_{route['dest_topic']}"

# ================================
# SAFE TELEGRAM LINK GENERATOR
# ================================
def generate_private_link(chat_id, message_id):
    try:
        clean_chat = str(chat_id).replace("-100", "")
        return f"https://t.me/c/{clean_chat}/{message_id}"
    except:
        return "LINK_ERROR"

# ================================
# ADMIN LOG SENDER
# ================================
def send_admin_log(text):
    try:
        bot.send_message(
            chat_id=VAULT_CHAT_ID,
            text=text,
            message_thread_id=ADMIN_LOG_TOPIC_ID
        )
    except Exception as e:
        print("Admin log send error:", e)

# ================================
# REGISTRY LOGGER
# ================================
def log_to_registry(original_message, route, sent_message):
    global VAULT_REGISTRY

    try:
        file_caption = original_message.caption if hasattr(original_message, "caption") and original_message.caption else ""
        if not file_caption and hasattr(original_message, "text"):
            file_caption = original_message.text or ""

        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_chat": original_message.chat.id,
            "source_topic": getattr(original_message, "message_thread_id", None),
            "source_message_id": original_message.message_id,
            "dest_chat": route["dest_chat"],
            "dest_topic": route["dest_topic"],
            "dest_message_id": sent_message.message_id,
            "caption": file_caption,
            "vault_link": generate_private_link(route["dest_chat"], sent_message.message_id)
        }

        VAULT_REGISTRY.append(entry)
        save_registry(VAULT_REGISTRY)

        log_text = (
            f"✅ <b>NEW FILE STORED</b>\n"
            f"📝 <b>Caption:</b> {file_caption[:80]}\n"
            f"📦 <b>Vault Topic:</b> {route['dest_topic']}\n"
            f"🆔 <b>Msg ID:</b> {sent_message.message_id}\n"
            f"🔗 <a href='{entry['vault_link']}'>Open Stored File</a>"
        )

        send_admin_log(log_text)

    except Exception as e:
        print("Registry log error:", e)

# ================================
# ROUTE WORKER
# ================================
def route_worker(route):
    key = get_route_key(route)
    q = route_queues[key]

    while True:
        message = q.get()
        try:
            delay = route.get("delay", 0)
            time.sleep(delay)

            src_chat = message.chat.id

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

            # SAVE EVERY DESTINATION COPY INTO REGISTRY
            log_to_registry(message, route, sent)

        except Exception as e:
            print("Queue worker copy error:", e)

        q.task_done()

# ================================
# ENSURE THREAD WORKER
# ================================
def ensure_worker(route):
    key = get_route_key(route)

    if key not in route_queues:
        route_queues[key] = Queue()

    if key not in route_workers:
        t = threading.Thread(target=route_worker, args=(route,), daemon=True)
        t.start()
        route_workers[key] = t

# ================================
# START COMMAND
# ================================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    if not is_admin(message):
        return

    txt = (
        "✅ <b>RelayMaster V2 MedicalVault Edition Online</b>\n\n"
        "/whoami - show telegram user id\n"
        "/id - get current chat and topic id\n"
        "/addroute sourcechat sourcetopic destchat desttopic delay\n"
        "/routes - show all active routes\n"
        "/delroute number\n"
        "/clearall - delete all routes\n"
        "/registrycount - total stored files in registry"
    )
    bot.reply_to(message, txt)

# ================================
# WHOAMI
# ================================
@bot.message_handler(commands=['whoami'])
def whoami_cmd(message):
    bot.reply_to(message, f"👤 YOUR TELEGRAM ID: <code>{message.from_user.id}</code>")

# ================================
# ID COMMAND
# ================================
@bot.message_handler(commands=['id'])
def id_cmd(message):
    if not is_admin(message):
        return

    chat_id = message.chat.id
    topic_id = getattr(message, "message_thread_id", None)

    bot.reply_to(
        message,
        f"🆔 CHAT ID: <code>{chat_id}</code>\n🧵 TOPIC ID: <code>{topic_id}</code>"
    )

# ================================
# ADD ROUTE
# ================================
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
        delay = int(parts[5])

        new_route = {
            "source_chat": source_chat,
            "source_topic": source_topic,
            "dest_chat": dest_chat,
            "dest_topic": dest_topic,
            "delay": delay
        }

        ROUTES.append(new_route)
        save_routes(ROUTES)
        ensure_worker(new_route)

        bot.reply_to(message, "✅ New MedicalVault route added successfully.")

    except Exception as e:
        bot.reply_to(
            message,
            f"❌ Usage:\n/addroute sourcechat sourcetopic destchat desttopic delay\n\nError: {e}"
        )

# ================================
# SHOW ROUTES
# ================================
@bot.message_handler(commands=['routes'])
def show_routes(message):
    if not is_admin(message):
        return

    if not ROUTES:
        bot.reply_to(message, "No active routes configured.")
        return

    txt = "📡 <b>ACTIVE MEDICALVAULT ROUTES</b>\n\n"

    for i, r in enumerate(ROUTES, start=1):
        txt += (
            f"{i}. FROM: {r['source_chat']} | Topic: {r['source_topic']}\n"
            f"TO: {r['dest_chat']} | Topic: {r['dest_topic']}\n"
            f"DELAY: {r.get('delay',0)} sec\n\n"
        )

    bot.reply_to(message, txt)

# ================================
# DELETE ROUTE
# ================================
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

# ================================
# CLEAR ALL ROUTES
# ================================
@bot.message_handler(commands=['clearall'])
def clear_all(message):
    global ROUTES, route_queues, route_workers

    if not is_admin(message):
        return

    ROUTES = []
    route_queues = {}
    route_workers = {}
    save_routes(ROUTES)

    bot.reply_to(message, "🗑 All routes cleared.")

# ================================
# REGISTRY COUNT
# ================================
@bot.message_handler(commands=['registrycount'])
def registry_count(message):
    if not is_admin(message):
        return

    total = len(VAULT_REGISTRY)
    bot.reply_to(message, f"📚 Total stored files in registry: <b>{total}</b>")

# ================================
# MAIN RELAY ENGINE
# ================================
def process_relay(message):
    global ROUTES, recent_relays

    try:
        src_chat = message.chat.id
        src_topic = getattr(message, "message_thread_id", None)

        signature = f"{src_chat}:{src_topic}:{message.message_id}"

        # STRONG DUPLICATE LOOP PROTECTION
        if signature in recent_relays:
            return

        # CLEAN OLD DUPLICATE CACHE PERIODICALLY
        if len(recent_relays) > 5000:
            recent_relays = set(list(recent_relays)[-1000:])

        for route in ROUTES:

            if src_chat != route["source_chat"]:
                continue

            if route["source_topic"] is not None and src_topic != route["source_topic"]:
                continue

            ensure_worker(route)
            key = get_route_key(route)
            route_queues[key].put(message)

    except Exception as e:
        print("Relay engine error:", e)

# ================================
# UNIVERSAL PRIVATE/GROUP MESSAGE HANDLER
# ================================
@bot.message_handler(
    func=lambda m: True,
    content_types=[
        'text',
        'photo',
        'video',
        'document',
        'audio',
        'voice',
        'sticker',
        'animation'
    ]
)
def universal_handler(message):
    process_relay(message)

# ================================
# CHANNEL POST HANDLER
# ================================
@bot.channel_post_handler(
    func=lambda m: True,
    content_types=[
        'text',
        'photo',
        'video',
        'document',
        'audio',
        'voice',
        'sticker',
        'animation'
    ]
)
def channel_handler(message):
    process_relay(message)

# ================================
# WEBHOOK RECEIVER
# ================================
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return "ok", 200

    except Exception:
        print("WEBHOOK ERROR:")
        traceback.print_exc()
        return "error", 500

# ================================
# HOME CHECK
# ================================
@app.route("/")
def home():
    return "RelayMaster V2 MedicalVault Running"

# ================================
# START ALL SAVED ROUTE WORKERS
# ================================
for route in ROUTES:
    ensure_worker(route)

# ================================
# RUN APP
# ================================
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
