import logging
import threading
import asyncio  # <-- ১. asyncio ইম্পোর্ট করা হয়েছে
from datetime import datetime, timezone

from flask import Flask
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)

import config
from database import init_db, SessionLocal, Rider
from handlers.start import (
    start, registration_start, reg_contact, reg_name, reg_location, cancel_reg,
    REG_NAME, REG_LOCATION
)
from handlers.rider import (
    go_online, go_offline, myinfo, receive_live_location,
    set_range_start, set_range_value, change_home_start, change_home_location,
    cancel_conv, RANGE_WAIT, CHANGE_HOME_WAIT
)
from handlers.admin import (
    admin_panel, add_vendor_start, add_vendor_tg, add_vendor_name,
    add_vendor_phone, add_vendor_loc, list_vendors, list_riders,
    set_rates_start, set_rates_value, search_start, search_value,
    suspend_user, unsuspend_user, stats, cancel_admin,
    ADD_VENDOR_TG, ADD_VENDOR_NAME, ADD_VENDOR_PHONE, ADD_VENDOR_LOC,
    SET_RATE_WAIT, SEARCH_WAIT, is_admin
)
from handlers.vendor import (
    vendor_menu, vendor_myinfo, start_normal_order, start_broadcast_order,
    receive_order_text, cancel_vendor, ORDER_TEXT_WAIT, BROADCAST_TEXT_WAIT
)
from handlers.order import (
    order_accept, order_reject, order_complete, order_cancel_reassign
)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ====================== KEEP-ALIVE (Render Free) ======================
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Food Delivery Rider Bot is running ✅", 200

@flask_app.route("/ping")
def ping():
    return "pong", 200

@flask_app.route("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}, 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=config.PORT, debug=False, use_reloader=False)

# ====================== BACKGROUND TASKS ======================
async def check_live_locations(context: ContextTypes.DEFAULT_TYPE):
    """Periodically mark riders offline if live location is stale."""
    session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        riders = session.query(Rider).filter(Rider.is_online == True).all()
        for r in riders:
            if r.last_location_update:
                # ensure timezone aware
                last = r.last_location_update
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                age = (now - last).total_seconds()
                if age > config.LIVE_LOCATION_TIMEOUT:
                    r.is_online = False
                    logger.info(f"Rider {r.telegram_id} set offline (stale location)")
        session.commit()
    finally:
        session.close()

# ====================== MAIN ======================
def main():
    # ২. asyncio Event Loop ম্যানুয়ালি সেটআপ করা হলো (RuntimeError সমাধানের জন্য)
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Init DB
    init_db()
    logger.info("Database initialized")

    # Build application
    app = Application.builder().token(config.BOT_TOKEN).build()

    # ----- Conversation: Registration -----
    reg_conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("registration", registration_start),
        ],
        states={
            REG_NAME: [
                MessageHandler(filters.CONTACT, reg_contact),
                MessageHandler(filters.TEXT & ~filters.COMMAND, reg_name),
            ],
            REG_LOCATION: [
                MessageHandler(filters.LOCATION, reg_location),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_reg)],
        allow_reentry=True,
    )
    app.add_handler(reg_conv)

    # ----- Conversation: Set Range -----
    range_conv = ConversationHandler(
        entry_points=[
            CommandHandler("range", set_range_start),
            CallbackQueryHandler(set_range_start, pattern="^rider_set_range$"),
        ],
        states={
            RANGE_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_range_value)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)],
    )
    app.add_handler(range_conv)

    # ----- Conversation: Change Home -----
    home_conv = ConversationHandler(
        entry_points=[
            CommandHandler("change_home_address", change_home_start),
            CallbackQueryHandler(change_home_start, pattern="^rider_change_home$"),
        ],
        states={
            CHANGE_HOME_WAIT: [MessageHandler(filters.LOCATION, change_home_location)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)],
    )
    app.add_handler(home_conv)

    # ----- Conversation: Add Vendor (Admin) -----
    add_vendor_conv = ConversationHandler(
        entry_points=[
            CommandHandler("add_vendor", add_vendor_start),
            CallbackQueryHandler(add_vendor_start, pattern="^admin_add_vendor$"),
        ],
        states={
            ADD_VENDOR_TG: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_vendor_tg)],
            ADD_VENDOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_vendor_name)],
            ADD_VENDOR_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_vendor_phone)],
            ADD_VENDOR_LOC: [
                MessageHandler(filters.LOCATION, add_vendor_loc),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_vendor_loc),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_admin)],
    )
    app.add_handler(add_vendor_conv)

    # ----- Conversation: Set Rates -----
    rates_conv = ConversationHandler(
        entry_points=[
            CommandHandler("set_rates", set_rates_start),
            CallbackQueryHandler(set_rates_start, pattern="^admin_set_rates$"),
        ],
        states={
            SET_RATE_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_rates_value)],
        },
        fallbacks=[CommandHandler("cancel", cancel_admin)],
    )
    app.add_handler(rates_conv)

    # ----- Conversation: Search -----
    search_conv = ConversationHandler(
        entry_points=[CommandHandler("search", search_start)],
        states={
            SEARCH_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_value)],
        },
        fallbacks=[CommandHandler("cancel", cancel_admin)],
    )
    app.add_handler(search_conv)

    # ----- Conversation: Vendor Order -----
    order_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_normal_order, pattern="^vendor_order_normal$"),
            CallbackQueryHandler(start_broadcast_order, pattern="^vendor_order_broadcast$"),
        ],
        states={
            ORDER_TEXT_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_order_text)],
            BROADCAST_TEXT_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_order_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel_vendor)],
    )
    app.add_handler(order_conv)

    # ----- Simple Commands -----
    app.add_handler(CommandHandler("go_online", go_online))
    app.add_handler(CommandHandler("go_offline", go_offline))
    app.add_handler(CommandHandler("myinfo", myinfo))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("vendor", vendor_menu))
    app.add_handler(CommandHandler("list_vendors", list_vendors))
    app.add_handler(CommandHandler("list_riders", list_riders))
    app.add_handler(CommandHandler("suspend", suspend_user))
    app.add_handler(CommandHandler("unsuspend", unsuspend_user))
    app.add_handler(CommandHandler("stats", stats))

    # ----- Callback Queries -----
    app.add_handler(CallbackQueryHandler(go_online, pattern="^rider_go_online$"))
    app.add_handler(CallbackQueryHandler(go_offline, pattern="^rider_go_offline$"))
    app.add_handler(CallbackQueryHandler(list_vendors, pattern="^admin_list_vendors$"))
    app.add_handler(CallbackQueryHandler(list_riders, pattern="^admin_list_riders$"))
    app.add_handler(CallbackQueryHandler(vendor_myinfo, pattern="^vendor_myinfo$"))

    app.add_handler(CallbackQueryHandler(order_accept, pattern="^order_accept_"))
    app.add_handler(CallbackQueryHandler(order_reject, pattern="^order_reject_"))
    app.add_handler(CallbackQueryHandler(order_complete, pattern="^order_complete_"))
    app.add_handler(CallbackQueryHandler(order_cancel_reassign, pattern="^order_cancel_"))

    # Location updates (live location)
    app.add_handler(MessageHandler(filters.LOCATION, receive_live_location))

    # Periodic job: check stale live locations every 60s
    if app.job_queue:
        app.job_queue.run_repeating(check_live_locations, interval=60, first=10)

    # Start Flask keep-alive in background thread
    if getattr(config, 'KEEP_ALIVE', True):
        t = threading.Thread(target=run_flask, daemon=True)
        t.start()
        logger.info(f"Keep-alive Flask started on port {config.PORT}")

    # Run bot
    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
