from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import SessionLocal, Vendor
import config

ORDER_TEXT_WAIT = 30
BROADCAST_TEXT_WAIT = 31

def is_vendor(user_id: int) -> bool:
    session = SessionLocal()
    try:
        v = session.query(Vendor).filter_by(telegram_id=user_id, is_suspended=False).first()
        return v is not None
    finally:
        session.close()

async def vendor_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_vendor(user.id):
        await update.message.reply_text("আপনি Vendor হিসেবে রেজিস্টার্ড নন। Admin-এর সাথে যোগাযোগ করুন।")
        return

    text = (
        "🏪 Vendor Menu\n\n"
        "অর্ডার পোস্ট করতে নিচের বাটন ব্যবহার করুন।\n"
        "• Order → Vendor থেকে ১ কিমি এর মধ্যে Rider খুঁজবে\n"
        "• Broadcast → ৫ কিমি পর্যন্ত + extra pay"
    )
    keyboard = [
        [
            InlineKeyboardButton("📦 Order (Normal 1km)", callback_data="vendor_order_normal"),
            InlineKeyboardButton("📢 Broadcast (5km)", callback_data="vendor_order_broadcast"),
        ],
        [InlineKeyboardButton("ℹ️ My Info", callback_data="vendor_myinfo")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def vendor_myinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    session = SessionLocal()
    try:
        v = session.query(Vendor).filter_by(telegram_id=user_id).first()
        if not v:
            await query.edit_message_text("Vendor পাওয়া যায়নি।")
            return
        text = (
            f"🏪 {v.name}\n"
            f"📱 {v.phone}\n"
            f"📍 {v.lat:.5f}, {v.lon:.5f}\n"
            f"Status: {'🚫 Suspended' if v.is_suspended else '✅ Active'}"
        )
        await query.edit_message_text(text)
    finally:
        session.close()

async def start_normal_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_vendor(query.from_user.id):
        return
    context.user_data["order_type"] = "normal"
    await query.message.reply_text(
        "📦 Normal Order\n\n"
        "অর্ডারের বিবরণ + Customer-এর Google Maps Link একসাথে পাঠান।\n\n"
        "উদাহরণ:\n"
        "২ পিস বার্গার, ১ কোক\n"
        "https://maps.app.goo.gl/xxxxx\n\n"
        "অথবা\n"
        "Customer location: 23.81,90.41"
    )
    return ORDER_TEXT_WAIT

async def start_broadcast_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_vendor(query.from_user.id):
        return
    context.user_data["order_type"] = "broadcast"
    await query.message.reply_text(
        "📢 Broadcast Order (৫ কিমি)\n\n"
        "অর্ডারের বিবরণ + Customer-এর Google Maps Link একসাথে পাঠান।\n"
        "Broadcast-এ Rider-কে extra টাকা দিতে হবে (দূরত্ব অনুযায়ী)।"
    )
    return BROADCAST_TEXT_WAIT

async def receive_order_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Common handler after text is received. Actual matching is in order.py"""
    from handlers.order import create_and_dispatch_order

    text = update.message.text or ""
    order_type = context.user_data.get("order_type", "normal")
    user_id = update.effective_user.id

    await update.message.reply_text("অর্ডার প্রসেস করা হচ্ছে... অনুগ্রহ করে অপেক্ষা করুন।")
    result = await create_and_dispatch_order(
        context=context,
        vendor_telegram_id=user_id,
        order_text=text,
        order_type=order_type
    )
    await update.message.reply_text(result)
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_vendor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("বাতিল করা হয়েছে।")
    context.user_data.clear()
    return ConversationHandler.END
