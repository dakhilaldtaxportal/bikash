from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import SessionLocal, Rider, Vendor, Setting, set_setting, get_setting
import config

# States
ADD_VENDOR_TG, ADD_VENDOR_NAME, ADD_VENDOR_PHONE, ADD_VENDOR_LOC = range(20, 24)
SET_RATE_WAIT = 25
SEARCH_WAIT = 26

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("এই কমান্ড শুধুমাত্র Admin-এর জন্য।")
        return

    text = (
        "🛠 Admin Panel\n\n"
        "কমান্ডসমূহ:\n"
        "/add_vendor - নতুন Vendor যোগ করুন\n"
        "/list_vendors - সব Vendor দেখুন\n"
        "/list_riders - সব Rider দেখুন\n"
        "/search - নাম্বার দিয়ে সার্চ\n"
        "/set_rates - ডেলিভারি রেট পরিবর্তন\n"
        "/suspend - কাউকে suspend\n"
        "/unsuspend - unsuspend\n"
        "/stats - স্ট্যাটিসটিক্স"
    )
    keyboard = [
        [InlineKeyboardButton("➕ Add Vendor", callback_data="admin_add_vendor")],
        [InlineKeyboardButton("📋 List Vendors", callback_data="admin_list_vendors")],
        [InlineKeyboardButton("👥 List Riders", callback_data="admin_list_riders")],
        [InlineKeyboardButton("⚙️ Set Rates", callback_data="admin_set_rates")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def add_vendor_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        if not is_admin(query.from_user.id):
            return
        await query.message.reply_text(
            "Vendor-এর Telegram ID দিন (সংখ্যা):\n"
            "অথবা Vendor যে অ্যাকাউন্ট থেকে বট ব্যবহার করবে তার ID।"
        )
    else:
        if not is_admin(update.effective_user.id):
            return
        await update.message.reply_text("Vendor-এর Telegram ID দিন:")
    return ADD_VENDOR_TG

async def add_vendor_tg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        tg_id = int(update.message.text.strip())
    except (ValueError, AttributeError):
        await update.message.reply_text("সঠিক Telegram ID (সংখ্যা) দিন।")
        return ADD_VENDOR_TG

    context.user_data["new_vendor_tg"] = tg_id
    await update.message.reply_text("Vendor-এর নাম লিখুন:")
    return ADD_VENDOR_NAME

async def add_vendor_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("সঠিক নাম দিন।")
        return ADD_VENDOR_NAME
    context.user_data["new_vendor_name"] = name
    await update.message.reply_text("Vendor-এর ফোন নাম্বার দিন:")
    return ADD_VENDOR_PHONE

async def add_vendor_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    context.user_data["new_vendor_phone"] = phone
    await update.message.reply_text(
        "এখন Vendor-এর Current Location শেয়ার করুন "
        "(অথবা lat,lon ফরম্যাটে লিখুন যেমন: 23.8103,90.4125):"
    )
    return ADD_VENDOR_LOC

async def add_vendor_loc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lat, lon = None, None
    if update.message.location:
        lat = update.message.location.latitude
        lon = update.message.location.longitude
    else:
        try:
            parts = update.message.text.strip().replace(" ", "").split(",")
            lat = float(parts[0])
            lon = float(parts[1])
        except Exception:
            await update.message.reply_text("লোকেশন শেয়ার করুন অথবা lat,lon লিখুন।")
            return ADD_VENDOR_LOC

    tg_id = context.user_data.get("new_vendor_tg")
    name = context.user_data.get("new_vendor_name")
    phone = context.user_data.get("new_vendor_phone")

    session = SessionLocal()
    try:
        existing = session.query(Vendor).filter_by(telegram_id=tg_id).first()
        if existing:
            existing.name = name
            existing.phone = phone
            existing.lat = lat
            existing.lon = lon
            existing.added_by = update.effective_user.id
            msg = "Vendor আপডেট হয়েছে।"
        else:
            v = Vendor(
                telegram_id=tg_id,
                name=name,
                phone=phone,
                lat=lat,
                lon=lon,
                added_by=update.effective_user.id
            )
            session.add(v)
            msg = "Vendor সফলভাবে যোগ হয়েছে।"
        session.commit()
        await update.message.reply_text(f"✅ {msg}\nনাম: {name}\nPhone: {phone}\nLoc: {lat:.5f},{lon:.5f}")
    finally:
        session.close()

    context.user_data.clear()
    return ConversationHandler.END

async def list_vendors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id
    if not is_admin(user_id):
        return

    session = SessionLocal()
    try:
        vendors = session.query(Vendor).all()
        if not vendors:
            text = "কোনো Vendor নেই।"
        else:
            lines = []
            for v in vendors:
                status = "🚫 Suspended" if v.is_suspended else "✅ Active"
                lines.append(f"ID:{v.id} | {v.name} | {v.phone} | TG:{v.telegram_id} | {status}")
            text = "📋 Vendors:\n\n" + "\n".join(lines)
    finally:
        session.close()

    if query:
        await query.answer()
        await query.message.reply_text(text)
    else:
        await update.message.reply_text(text)

async def list_riders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id
    if not is_admin(user_id):
        return

    session = SessionLocal()
    try:
        riders = session.query(Rider).all()
        if not riders:
            text = "কোনো Rider নেই।"
        else:
            lines = []
            for r in riders:
                status = "🟢" if r.is_online else "🔴"
                sus = "🚫" if r.is_suspended else ""
                busy = "Busy" if r.is_busy else ""
                lines.append(f"{status}{sus} {r.name} | {r.phone} | TG:{r.telegram_id} | Range:{r.range_km} {busy}")
            text = "👥 Riders:\n\n" + "\n".join(lines)
    finally:
        session.close()

    if query:
        await query.answer()
        await query.message.reply_text(text)
    else:
        await update.message.reply_text(text)

async def set_rates_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        if not is_admin(query.from_user.id):
            return
        msg = query.message
    else:
        if not is_admin(update.effective_user.id):
            return
        msg = update.message

    base_km = get_setting("base_km", "3")
    base_price = get_setting("base_price", "50")
    extra = get_setting("extra_per_km", "20")
    bcast = get_setting("broadcast_per_km", "15")

    text = (
        f"বর্তমান রেট:\n"
        f"Base: {base_km} km পর্যন্ত {base_price} টাকা\n"
        f"Extra: প্রতি km {extra} টাকা\n"
        f"Broadcast extra: প্রতি km {bcast} টাকা\n\n"
        "নতুন রেট সেট করতে এই ফরম্যাটে লিখুন:\n"
        "`base_km,base_price,extra_per_km,broadcast_per_km`\n"
        "উদাহরণ: `3,50,20,15`"
    )
    await msg.reply_text(text, parse_mode="Markdown")
    return SET_RATE_WAIT

async def set_rates_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    try:
        parts = [p.strip() for p in update.message.text.split(",")]
        base_km, base_price, extra, bcast = parts[0], parts[1], parts[2], parts[3]
        float(base_km); float(base_price); float(extra); float(bcast)
        set_setting("base_km", base_km)
        set_setting("base_price", base_price)
        set_setting("extra_per_km", extra)
        set_setting("broadcast_per_km", bcast)
        await update.message.reply_text("✅ রেট আপডেট হয়েছে।")
    except Exception:
        await update.message.reply_text("সঠিক ফরম্যাট দিন: base_km,base_price,extra_per_km,broadcast_per_km")
        return SET_RATE_WAIT
    return ConversationHandler.END

async def search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("ফোন নাম্বার বা Telegram ID দিন সার্চ করার জন্য:")
    return SEARCH_WAIT

async def search_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    q = update.message.text.strip()
    session = SessionLocal()
    try:
        # try rider
        riders = session.query(Rider).filter(
            (Rider.phone.contains(q)) | (Rider.telegram_id == int(q) if q.isdigit() else False)
        ).all() if q else []
        vendors = session.query(Vendor).filter(
            (Vendor.phone.contains(q)) | (Vendor.telegram_id == int(q) if q.isdigit() else False)
        ).all() if q else []

        lines = []
        for r in riders:
            lines.append(f"[Rider] {r.name} | {r.phone} | TG:{r.telegram_id} | Online:{r.is_online} | Sus:{r.is_suspended}")
        for v in vendors:
            lines.append(f"[Vendor] {v.name} | {v.phone} | TG:{v.telegram_id} | Sus:{v.is_suspended}")

        text = "\n".join(lines) if lines else "কিছু পাওয়া যায়নি।"
        await update.message.reply_text(text)
    finally:
        session.close()
    return ConversationHandler.END

async def suspend_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("ব্যবহার: /suspend <telegram_id>")
        return
    try:
        tg_id = int(args[0])
    except ValueError:
        await update.message.reply_text("সঠিক telegram_id দিন।")
        return

    session = SessionLocal()
    try:
        rider = session.query(Rider).filter_by(telegram_id=tg_id).first()
        vendor = session.query(Vendor).filter_by(telegram_id=tg_id).first()
        if rider:
            rider.is_suspended = True
            rider.is_online = False
            session.commit()
            await update.message.reply_text(f"Rider {tg_id} suspended।")
        elif vendor:
            vendor.is_suspended = True
            session.commit()
            await update.message.reply_text(f"Vendor {tg_id} suspended।")
        else:
            await update.message.reply_text("পাওয়া যায়নি।")
    finally:
        session.close()

async def unsuspend_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if not args:
        await update.message.reply_text("ব্যবহার: /unsuspend <telegram_id>")
        return
    try:
        tg_id = int(args[0])
    except ValueError:
        await update.message.reply_text("সঠিক telegram_id দিন।")
        return

    session = SessionLocal()
    try:
        rider = session.query(Rider).filter_by(telegram_id=tg_id).first()
        vendor = session.query(Vendor).filter_by(telegram_id=tg_id).first()
        if rider:
            rider.is_suspended = False
            session.commit()
            await update.message.reply_text(f"Rider {tg_id} unsuspended।")
        elif vendor:
            vendor.is_suspended = False
            session.commit()
            await update.message.reply_text(f"Vendor {tg_id} unsuspended।")
        else:
            await update.message.reply_text("পাওয়া যায়নি।")
    finally:
        session.close()

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    session = SessionLocal()
    try:
        total_riders = session.query(Rider).count()
        online = session.query(Rider).filter_by(is_online=True).count()
        total_vendors = session.query(Vendor).count()
        from database import Order
        total_orders = session.query(Order).count()
        text = (
            f"📊 Stats\n"
            f"Riders: {total_riders} (Online: {online})\n"
            f"Vendors: {total_vendors}\n"
            f"Orders: {total_orders}"
        )
        await update.message.reply_text(text)
    finally:
        session.close()

async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("বাতিল।")
    return ConversationHandler.END
