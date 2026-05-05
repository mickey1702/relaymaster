import os
import json
import telebot
import traceback
import threading
import time
from queue import Queue
from flask import Flask, request
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = str(os.getenv("ADMIN_ID", "0")).strip()

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=False)
app = Flask(__name__)

ROUTE_FILE = "routes.json"
recent_relays = set()
route_queues = {}
route_workers = {}
user_sessions = {}

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

def is_admin(message):
    return True
    
def main_panel():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ Add Route", callback_data="addroute"),
        InlineKeyboardButton("📡 View Routes", callback_data="viewroutes"),
        InlineKeyboardButton("⏯ Toggle Route", callback_data="toggle"),
        InlineKeyboardButton("🗑 Delete Route", callback_data="delete"),
        InlineKeyboardButton("📝 Caption Mode", callback_data="caption"),
        InlineKeyboardButton("📊 Log Panel", callback_data="stats")
    )
    return kb

def get_route_key(route):
    return f"{route['source_chat']}_{route['source_topic']}_{route['dest_chat']}_{route['dest_topic']}"

def route_worker(route):
    key = get_route_key(route)
    q = route_queues[key]

    while True:
        message = q.get()
        try:
            delay = route.get("delay", 0)
            time.sleep(delay)

            src_chat = message.chat.id
            prefix = route.get("prefix", "")

            original_caption = ""
            if hasattr(message, "caption") and message.caption:
                original_caption = message.caption
            elif hasattr(message, "text") and message.text:
                original_caption = message.text

            final_caption = f"{prefix}{original_caption}" if prefix else original_caption

            if message.content_type == "text":
                if route["dest_topic"] is not None:
                    sent = bot.send_message(
                        route["dest_chat"],
                        final_caption,
                        message_thread_id=route["dest_topic"]
                    )
                else:
                    sent = bot.send_message(
                        route["dest_chat"],
                        final_caption
                    )

            else:
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
            print("Queue worker copy error:", e)

        q.task_done()

def ensure_worker(route):
    key = get_route_key(route)
    if key not in route_queues:
        route_queues[key] = Queue()

    if key not in route_workers:
        t = threading.Thread(target=route_worker, args=(route,), daemon=True)
        t.start()
        route_workers[key] = t

@bot.message_handler(commands=['start'])
def start_cmd(message):
    txt = """<b>TSD AUTOFORWARD PRO CONSOLE</b>

Intelligent Telegram Routing & Mirroring Utility

------------------------------
• Topic ↔ Topic Relay
• Group ↔ Channel Forwarding
• Sequential Delay Queue Engine
• Caption Prefix Management
• Route Status Controller
• Live Route Statistics
------------------------------

<b>System Status:</b> 🟢 ONLINE

Use the control panel below."""
    
    bot.send_message(message.chat.id, txt, reply_markup=main_panel())

@bot.callback_query_handler(func=lambda call: True)
def callback_router(call):
    global ROUTES, user_sessions

    try:
        uid = call.from_user.id

        if call.data == "viewroutes":
            if not ROUTES:
                bot.answer_callback_query(call.id, "No routes configured.")
                return

            txt = "📡 <b>ACTIVE ROUTING TABLE</b>\n\n"
            for i, r in enumerate(ROUTES, start=1):
                state = "🟢 ON" if r.get("enabled", True) else "🔴 OFF"
                txt += (
                    f"{i}. {state}\n"
                    f"FROM: {r['source_chat']} | {r['source_topic']}\n"
                    f"TO: {r['dest_chat']} | {r['dest_topic']}\n"
                    f"DELAY: {r.get('delay',0)} sec\n"
                    f"PREFIX: {r.get('prefix','(none)')}\n\n"
                )
            bot.send_message(call.message.chat.id, txt)

        elif call.data == "stats":
            total = len(ROUTES)
            active = len([r for r in ROUTES if r.get("enabled", True)])
            paused = total - active

            txt = (
                "📊 <b>TSD ROUTE LOG PANEL</b>\n\n"
                f"Total Routes: {total}\n"
                f"Active Routes: {active}\n"
                f"Paused Routes: {paused}\n"
                f"Queue Workers Running: {len(route_workers)}"
            )
            bot.send_message(call.message.chat.id, txt)

        elif call.data == "addroute":
            user_sessions[uid] = {"mode": "addroute_step1"}
            bot.send_message(call.message.chat.id, "➕ Send SOURCE CHAT ID")

        elif call.data == "toggle":
            if not ROUTES:
                bot.answer_callback_query(call.id, "No routes available.")
                return
            user_sessions[uid] = {"mode": "toggle_route"}
            bot.send_message(call.message.chat.id, "⏯ Send route number to toggle ON/OFF")

        elif call.data == "delete":
            if not ROUTES:
                bot.answer_callback_query(call.id, "No routes available.")
                return
            user_sessions[uid] = {"mode": "delete_route"}
            bot.send_message(call.message.chat.id, "🗑 Send route number to delete")

        elif call.data == "caption":
            if not ROUTES:
                bot.answer_callback_query(call.id, "No routes available.")
                return
            user_sessions[uid] = {"mode": "caption_route_select"}
            bot.send_message(call.message.chat.id, "📝 Send route number to set caption prefix")

        else:
            bot.answer_callback_query(call.id, "Unknown action.")

    except Exception as e:
        print("Callback error:", e)

@bot.message_handler(commands=['whoami'])
def whoami_cmd(message):
    bot.reply_to(message, f"👤 YOUR TELEGRAM ID: <code>{message.from_user.id}</code>")

@bot.message_handler(commands=['id'])
def id_cmd(message):
    if not is_admin(message):
        return
    chat_id = message.chat.id
    topic_id = getattr(message, "message_thread_id", None)
    bot.reply_to(message, f"🆔 CHAT ID: <code>{chat_id}</code>\n🧵 TOPIC ID: <code>{topic_id}</code>")

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
    "delay": delay,
    "enabled": True,
    "prefix": "",
    "strip_caption": False
        }

        ROUTES.append(new_route)
        save_routes(ROUTES)
        ensure_worker(new_route)
        bot.reply_to(message, "✅ Portable route added successfully.")

    except Exception as e:
        bot.reply_to(message, f"❌ Usage:\n/addroute sourcechat sourcetopic destchat desttopic delay\n\nError: {e}")

@bot.message_handler(commands=['routes'])
def show_routes(message):
    if not is_admin(message):
        return
    if not ROUTES:
        bot.reply_to(message, "No routes configured.")
        return
    txt = "📡 ACTIVE PORTABLE ROUTES:\n\n"
    for i, r in enumerate(ROUTES, start=1):
        txt += f"{i}. FROM: {r['source_chat']} | Topic: {r['source_topic']}\nTO: {r['dest_chat']} | Topic: {r['dest_topic']}\nDELAY: {r.get('delay',0)} sec\n\n"
    bot.reply_to(message, txt)

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
def process_user_session(message):
    global user_sessions, ROUTES

    uid = message.from_user.id

    if uid not in user_sessions:
        return False

    session = user_sessions[uid]
    mode = session["mode"]

    try:
        # ADD ROUTE WIZARD
        if mode == "addroute_step1":
            session["source_chat"] = int(message.text)
            session["mode"] = "addroute_step2"
            bot.reply_to(message, "Send SOURCE TOPIC ID (or type none)")

        elif mode == "addroute_step2":
            session["source_topic"] = None if message.text.lower() == "none" else int(message.text)
            session["mode"] = "addroute_step3"
            bot.reply_to(message, "Send DESTINATION CHAT ID")

        elif mode == "addroute_step3":
            session["dest_chat"] = int(message.text)
            session["mode"] = "addroute_step4"
            bot.reply_to(message, "Send DESTINATION TOPIC ID (or type none)")

        elif mode == "addroute_step4":
            session["dest_topic"] = None if message.text.lower() == "none" else int(message.text)
            session["mode"] = "addroute_step5"
            bot.reply_to(message, "Send DELAY in seconds")

        elif mode == "addroute_step5":
            delay = int(message.text)

            new_route = {
                "source_chat": session["source_chat"],
                "source_topic": session["source_topic"],
                "dest_chat": session["dest_chat"],
                "dest_topic": session["dest_topic"],
                "delay": delay,
                "enabled": True,
                "prefix": "",
                "strip_caption": False
            }

            ROUTES.append(new_route)
            save_routes(ROUTES)
            ensure_worker(new_route)
            bot.reply_to(message, "✅ New route created from control panel.")
            del user_sessions[uid]

        # TOGGLE ROUTE
        elif mode == "toggle_route":
            num = int(message.text) - 1
            if 0 <= num < len(ROUTES):
                ROUTES[num]["enabled"] = not ROUTES[num].get("enabled", True)
                save_routes(ROUTES)
                state = "ON" if ROUTES[num]["enabled"] else "OFF"
                bot.reply_to(message, f"⏯ Route {num+1} switched {state}")
            del user_sessions[uid]

        # DELETE ROUTE
        elif mode == "delete_route":
            num = int(message.text) - 1
            if 0 <= num < len(ROUTES):
                ROUTES.pop(num)
                save_routes(ROUTES)
                bot.reply_to(message, "🗑 Route deleted successfully.")
            del user_sessions[uid]

        # CAPTION PREFIX
        elif mode == "caption_route_select":
            num = int(message.text) - 1
            session["route_num"] = num
            session["mode"] = "caption_route_write"
            bot.reply_to(message, "Send prefix text to add before every caption")

        elif mode == "caption_route_write":
            num = session["route_num"]
            if 0 <= num < len(ROUTES):
                ROUTES[num]["prefix"] = message.text
                save_routes(ROUTES)
                bot.reply_to(message, "📝 Caption prefix saved.")
            del user_sessions[uid]

    except Exception as e:
        bot.reply_to(message, f"❌ Session Error: {e}")
        if uid in user_sessions:
            del user_sessions[uid]

    return True
def process_relay(message):
    global ROUTES, recent_relays
    try:
        src_chat = message.chat.id
        src_topic = getattr(message, "message_thread_id", None)

        signature = f"{src_chat}:{src_topic}:{message.message_id}"
        if signature in recent_relays:
            return

        for route in ROUTES:
            if not route.get("enabled", True):
                continue
            if src_chat != route["source_chat"]:
                continue
            if route["source_topic"] is not None and src_topic != route["source_topic"]:
                continue

            ensure_worker(route)
            key = get_route_key(route)
            route_queues[key].put(message)

    except Exception as e:
        print("Relay engine error:", e)

@bot.message_handler(func=lambda m: True, content_types=['text','photo','video','document','audio','voice','sticker','animation'])
def universal_handler(message):
    if process_user_session(message):
        return
    process_relay(message)
@bot.channel_post_handler(func=lambda m: True, content_types=['text','photo','video','document','audio','voice','sticker','animation'])
def channel_handler(message):
    process_relay(message)

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

@app.route("/")
def home():
    return "RelayMaster Portable Final Running"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
