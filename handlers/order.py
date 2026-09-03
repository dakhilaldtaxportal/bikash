import asyncio
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import (
    SessionLocal, Rider, Vendor, Order, OrderType, OrderStatus,
    get_setting
)
from utils.distance import get_road_distance_km, calculate_delivery_charge, calculate_broadcast_extra
from utils.location import extract_lat_lon_from_text
import config
import logging

logger = logging.getLogger(__name__)

# In-memory tracking of pending order messages for timeout
# order_id -> list of (chat_id, message_id)
pending_order_messages = {}

async def create_and_dispatch_order(context: ContextTypes.DEFAULT_TYPE, vendor_telegram_id: int,
                                   order_text: str, order_type: str = "normal") -> str:
    session = SessionLocal()
    try:
        vendor = session.query(Vendor).filter_by(telegram_id=vendor_telegram_id, is_suspended=False).first()
        if not vendor:
            return "❌ Vendor পাওয়া যায়নি বা Suspended।"

        # Extract customer location
        customer_lat, customer_lon = None, None
        extracted = await extract_lat_lon_from_text(order_text)
        if extracted:
            customer_lat, customer_lon = extracted
        else:
            return "❌ Customer-এর Google Maps link বা lat,lon পাওয়া যায়নি। লিংকসহ আবার পাঠান।"

        # Calculate vendor -> customer distance
        dist_vc = await get_road_distance_km(vendor.lat, vendor.lon, customer_lat, customer_lon)

        base_km = float(get_setting("base_km", "3"))
        base_price = float(get_setting("base_price", "50"))
        extra_per_km = float(get_setting("extra_per_km", "20"))
        delivery_charge = calculate_delivery_charge(dist_vc, base_km, base_price, extra_per_km)

        otype = OrderType.BROADCAST if order_type == "broadcast" else OrderType.NORMAL
        radius = float(get_setting("broadcast_radius", str(config.BROADCAST_RADIUS_KM))) if otype == OrderType.BROADCAST \
            else float(get_setting("normal_radius", str(config.NORMAL_RADIUS_KM)))

        order = Order(
            vendor_id=vendor.id,
            order_text=order_text,
            customer_map_link=order_text,  # keep full text
            customer_lat=customer_lat,
            customer_lon=customer_lon,
            order_type=otype,
            status=OrderStatus.PENDING,
            delivery_charge=delivery_charge,
            distance_vendor_customer_km=dist_vc,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=config.ACCEPT_TIMEOUT_SECONDS)
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        # Find eligible riders
        riders = session.query(Rider).filter(
            Rider.is_online == True,
            Rider.is_suspended == False,
            Rider.is_busy == False,
            Rider.home_lat.isnot(None),
            Rider.current_lat.isnot(None)
        ).all()

        eligible = []
        for r in riders:
            # Check live location freshness
            if r.last_location_update:
                age = (datetime.now(timezone.utc) - r.last_location_update.replace(tzinfo=timezone.utc)).total_seconds()
                if age > config.LIVE_LOCATION_TIMEOUT:
                    r.is_online = False
                    continue

            # Distance vendor -> rider
            dist_vr = await get_road_distance_km(vendor.lat, vendor.lon, r.current_lat, r.current_lon)
            if dist_vr > radius:
                continue

            # Both vendor and customer must be within rider's home range
            dist_home_vendor = await get_road_distance_km(r.home_lat, r.home_lon, vendor.lat, vendor.lon)
            dist_home_customer = await get_road_distance_km(r.home_lat, r.home_lon, customer_lat, customer_lon)
            if dist_home_vendor > r.range_km or dist_home_customer > r.range_km:
                continue

            broadcast_extra = 0.0
            if otype == OrderType.BROADCAST:
                per_km = float(get_setting("broadcast_per_km", str(config.DEFAULT_BROADCAST_PER_KM)))
                broadcast_extra = calculate_broadcast_extra(dist_vr, per_km)

            eligible.append({
                "rider": r,
                "dist_vr": dist_vr,
                "broadcast_extra": broadcast_extra
            })

        session.commit()  # save any offline changes

        if not eligible:
            order.status = OrderStatus.EXPIRED
            session.commit()
            return (
                f"⚠️ কোনো উপযুক্ত Rider পাওয়া যায়নি।\n"
                f"Vendor→Customer: {dist_vc:.2f} km\n"
                f"Delivery Charge: {delivery_charge} টাকা\n"
                f"Search radius: {radius} km"
            )

        # Sort by distance (nearest first)
        eligible.sort(key=lambda x: x["dist_vr"])

        # Send to all eligible (first accept wins). Track messages for timeout.
        pending_order_messages[order.id] = []

        for item in eligible:
            r = item["rider"]
            extra = item["broadcast_extra"]
            dist_vr = item["dist_vr"]

            # Update order temporarily for this rider view (we don't assign yet)
            text = (
                f"📦 নতুন অর্ডার #{order.id}\n"
                f"Type: {'📢 Broadcast' if otype == OrderType.BROADCAST else '📦 Normal'}\n\n"
                f"{order.order_text[:500]}\n\n"
                f"📍 Vendor থেকে আপনার দূরত্ব: {dist_vr:.2f} km\n"
                f"📍 Vendor → Customer: {dist_vc:.2f} km\n"
                f"💰 Delivery Charge (Customer দিবে): {delivery_charge} টাকা\n"
            )
            if otype == OrderType.BROADCAST and extra > 0:
                text += f"💸 Broadcast Extra (Vendor আপনাকে দিবে): {extra} টাকা\n"

            text += f"\n⏱ {config.ACCEPT_TIMEOUT_SECONDS} সেকেন্ডের মধ্যে Accept করুন।"

            keyboard = [
                [
                    InlineKeyboardButton("✅ Accept", callback_data=f"order_accept_{order.id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"order_reject_{order.id}"),
                ]
            ]
            try:
                sent = await context.bot.send_message(
                    chat_id=r.telegram_id,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                pending_order_messages[order.id].append((r.telegram_id, sent.message_id))
            except Exception as e:
                logger.warning(f"Could not send order to rider {r.telegram_id}: {e}")

        # Schedule timeout job
        context.job_queue.run_once(
            order_timeout_callback,
            when=config.ACCEPT_TIMEOUT_SECONDS,
            data={"order_id": order.id},
            name=f"timeout_{order.id}"
        )

        return (
            f"✅ অর্ডার #{order.id} পাঠানো হয়েছে {len(eligible)} জন Rider-কে।\n"
            f"Vendor→Customer: {dist_vc:.2f} km | Charge: {delivery_charge} টাকা\n"
            f"Type: {order_type} | Radius: {radius} km"
        )
    except Exception as e:
        logger.exception("create_and_dispatch_order failed")
        return f"❌ Error: {str(e)}"
    finally:
        session.close()

async def order_timeout_callback(context: ContextTypes.DEFAULT_TYPE):
    order_id = context.job.data["order_id"]
    session = SessionLocal()
    try:
        order = session.query(Order).filter_by(id=order_id).first()
        if order and order.status == OrderStatus.PENDING:
            order.status = OrderStatus.EXPIRED
            session.commit()

            # Notify riders that it expired
            msgs = pending_order_messages.pop(order_id, [])
            for chat_id, msg_id in msgs:
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_id,
                        text=f"⏱ অর্ডার #{order_id} এর সময় শেষ। আর Accept করা যাবে না।"
                    )
                except Exception:
                    pass
    finally:
        session.close()

async def order_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # order_accept_123
    try:
        order_id = int(data.split("_")[-1])
    except Exception:
        return

    user_id = query.from_user.id
    session = SessionLocal()
    try:
        order = session.query(Order).filter_by(id=order_id).first()
        if not order:
            await query.edit_message_text("অর্ডার পাওয়া যায়নি।")
            return

        if order.status != OrderStatus.PENDING:
            await query.edit_message_text(f"এই অর্ডার আর Available নেই। Status: {order.status.value}")
            return

        rider = session.query(Rider).filter_by(telegram_id=user_id).first()
        if not rider or rider.is_busy or not rider.is_online:
            await query.edit_message_text("আপনি এখন অর্ডার নিতে পারবেন না (Busy/Offline)।")
            return

        vendor = session.query(Vendor).filter_by(id=order.vendor_id).first()

        # Assign
        order.rider_id = rider.id
        order.status = OrderStatus.ACCEPTED
        order.accepted_at = datetime.now(timezone.utc)
        rider.is_busy = True

        # Calculate broadcast extra if needed
        if order.order_type == OrderType.BROADCAST and rider.current_lat:
            dist_vr = await get_road_distance_km(vendor.lat, vendor.lon, rider.current_lat, rider.current_lon)
            per_km = float(get_setting("broadcast_per_km", "15"))
            order.broadcast_extra = calculate_broadcast_extra(dist_vr, per_km)
            order.distance_vendor_rider_km = dist_vr

        session.commit()

        # Remove timeout job
        jobs = context.job_queue.get_jobs_by_name(f"timeout_{order_id}")
        for j in jobs:
            j.schedule_removal()

        # Edit all other pending messages
        msgs = pending_order_messages.pop(order_id, [])
        for chat_id, msg_id in msgs:
            if chat_id == user_id:
                continue
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=f"অর্ডার #{order_id} অন্য Rider Accept করেছে।"
                )
            except Exception:
                pass

        # Notify this rider
        keyboard = [
            [InlineKeyboardButton("✅ Delivery Complete", callback_data=f"order_complete_{order_id}")],
            [InlineKeyboardButton("⚠️ Cancel / Problem (Reassign)", callback_data=f"order_cancel_{order_id}")],
        ]
        text = (
            f"✅ আপনি অর্ডার #{order_id} Accept করেছেন!\n\n"
            f"{order.order_text[:400]}\n\n"
            f"🏪 Vendor: {vendor.name}\n"
            f"📞 Vendor Phone: {vendor.phone}\n"
            f"💰 Delivery Charge: {order.delivery_charge} টাকা\n"
        )
        if order.broadcast_extra > 0:
            text += f"💸 Broadcast Extra: {order.broadcast_extra} টাকা\n"
        text += "\nডেলিভারি শেষে Complete চাপুন। সমস্যা হলে Cancel চাপুন।"

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

        # Notify vendor
        try:
            await context.bot.send_message(
                chat_id=vendor.telegram_id,
                text=(
                    f"✅ অর্ডার #{order_id} Accept হয়েছে!\n"
                    f"Rider: {rider.name}\n"
                    f"📞 Rider Phone: {rider.phone}\n"
                    f"এখন একে অপরকে কল করতে পারেন।"
                )
            )
        except Exception:
            pass

    finally:
        session.close()

async def order_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Reject করা হয়েছে")
    data = query.data
    try:
        order_id = int(data.split("_")[-1])
    except Exception:
        return
    await query.edit_message_text(f"আপনি অর্ডার #{order_id} Reject করেছেন।")

async def order_complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    try:
        order_id = int(data.split("_")[-1])
    except Exception:
        return

    user_id = query.from_user.id
    session = SessionLocal()
    try:
        order = session.query(Order).filter_by(id=order_id).first()
        if not order or order.status != OrderStatus.ACCEPTED:
            await query.edit_message_text("অর্ডার Complete করা যাবে না।")
            return

        rider = session.query(Rider).filter_by(telegram_id=user_id).first()
        if not rider or order.rider_id != rider.id:
            await query.edit_message_text("এই অর্ডার আপনার নয়।")
            return

        order.status = OrderStatus.COMPLETED
        order.completed_at = datetime.now(timezone.utc)
        rider.is_busy = False
        session.commit()

        await query.edit_message_text(f"✅ অর্ডার #{order_id} Complete হয়েছে। আপনি আবার নতুন অর্ডার পেতে পারেন।")

        # Notify vendor
        vendor = session.query(Vendor).filter_by(id=order.vendor_id).first()
        if vendor and vendor.telegram_id:
            try:
                await context.bot.send_message(
                    chat_id=vendor.telegram_id,
                    text=f"✅ অর্ডার #{order_id} Rider কর্তৃক Complete করা হয়েছে।"
                )
            except Exception:
                pass
    finally:
        session.close()

async def order_cancel_reassign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rider cancels after accept → reassign to other nearby riders"""
    query = update.callback_query
    await query.answer()
    data = query.data
    try:
        order_id = int(data.split("_")[-1])
    except Exception:
        return

    user_id = query.from_user.id
    session = SessionLocal()
    try:
        order = session.query(Order).filter_by(id=order_id).first()
        if not order or order.status != OrderStatus.ACCEPTED:
            await query.edit_message_text("Cancel করা যাবে না।")
            return

        rider = session.query(Rider).filter_by(telegram_id=user_id).first()
        if not rider or order.rider_id != rider.id:
            await query.edit_message_text("এই অর্ডার আপনার নয়।")
            return

        # Free the rider
        rider.is_busy = False
        order.rider_id = None
        order.status = OrderStatus.PENDING
        order.accepted_at = None
        order.expires_at = datetime.now(timezone.utc) + timedelta(seconds=config.ACCEPT_TIMEOUT_SECONDS)
        session.commit()

        await query.edit_message_text(f"⚠️ অর্ডার #{order_id} Cancel করা হয়েছে। অন্য Rider-দের কাছে পাঠানো হচ্ছে...")

        # Re-dispatch (only normal radius now)
        vendor = session.query(Vendor).filter_by(id=order.vendor_id).first()
        # We call create logic partially - simpler to re-use dispatch by resetting type to normal
        # For simplicity, notify vendor and let them re-post, or implement quick re-dispatch

        # Quick re-dispatch to other riders within 1km
        from handlers.order import create_and_dispatch_order  # already in same module

        # Since order exists, we manually find and send again
        radius = float(get_setting("normal_radius", "1.0"))
        riders = session.query(Rider).filter(
            Rider.is_online == True,
            Rider.is_suspended == False,
            Rider.is_busy == False,
            Rider.telegram_id != user_id,
            Rider.current_lat.isnot(None)
        ).all()

        eligible_count = 0
        pending_order_messages[order.id] = []
        for r in riders:
            dist_vr = await get_road_distance_km(vendor.lat, vendor.lon, r.current_lat, r.current_lon)
            if dist_vr > radius:
                continue
            dist_home_v = await get_road_distance_km(r.home_lat, r.home_lon, vendor.lat, vendor.lon)
            dist_home_c = await get_road_distance_km(r.home_lat, r.home_lon, order.customer_lat, order.customer_lon)
            if dist_home_v > r.range_km or dist_home_c > r.range_km:
                continue

            text = (
                f"📦 Reassigned অর্ডার #{order.id}\n\n"
                f"{order.order_text[:400]}\n\n"
                f"Vendor থেকে দূরত্ব: {dist_vr:.2f} km\n"
                f"Delivery Charge: {order.delivery_charge} টাকা\n"
                f"⏱ {config.ACCEPT_TIMEOUT_SECONDS}s"
            )
            keyboard = [[
                InlineKeyboardButton("✅ Accept", callback_data=f"order_accept_{order.id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"order_reject_{order.id}"),
            ]]
            try:
                sent = await context.bot.send_message(
                    chat_id=r.telegram_id,
                    text=text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                pending_order_messages[order.id].append((r.telegram_id, sent.message_id))
                eligible_count += 1
            except Exception:
                pass

        if eligible_count == 0:
            order.status = OrderStatus.CANCELLED
            session.commit()
            await context.bot.send_message(
                chat_id=vendor.telegram_id,
                text=f"অর্ডার #{order.id} Cancel হয়েছে এবং নতুন Rider পাওয়া যায়নি।"
            )
        else:
            context.job_queue.run_once(
                order_timeout_callback,
                when=config.ACCEPT_TIMEOUT_SECONDS,
                data={"order_id": order.id},
                name=f"timeout_{order.id}"
            )
            await context.bot.send_message(
                chat_id=vendor.telegram_id,
                text=f"অর্ডার #{order.id} Rider cancel করেছে। {eligible_count} জন নতুন Rider-কে পাঠানো হয়েছে।"
            )
    finally:
        session.close()
