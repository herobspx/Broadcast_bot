import os
import io
import json
import logging
import asyncio
import httpx
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN  = os.environ["BROADCAST_TOKEN"]
SIGNALS_URL     = os.environ.get("SIGNALS_URL", "https://signalsbot-production.up.railway.app")
SUBSCRIBERS_DB  = "db.json"
BROADCAST_DB    = "broadcast_db.json"
PUBLIC_CHANNEL  = -1001934800979
BOT_LINK        = "t.me/BadrAI000_bot"

def load_subs_db():
    if os.path.exists(SUBSCRIBERS_DB):
        with open(SUBSCRIBERS_DB, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"subscribers": {}, "verified": {}}

def load_broadcast_db():
    if os.path.exists(BROADCAST_DB):
        with open(BROADCAST_DB, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"admin_id": None, "stats": []}

def save_broadcast_db(db):
    with open(BROADCAST_DB, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def get_admin():
    return load_broadcast_db().get("admin_id")

def set_admin(uid):
    db = load_broadcast_db()
    db["admin_id"] = uid
    save_broadcast_db(db)

def get_all_users():
    try:
        db    = load_subs_db()
        users = set()
        for uid in db.get("subscribers", {}).keys():
            users.add(uid)
        for uid in db.get("verified", {}).keys():
            users.add(uid)
        return list(users)
    except Exception as e:
        logger.error(f"Error loading subs DB: {e}")
        return []

def get_active_subscribers():
    try:
        db  = load_subs_db()
        now = datetime.now()
        active = []
        for uid, s in db.get("subscribers", {}).items():
            exp = datetime.fromisoformat(s["expires_at"])
            if now < exp:
                active.append(uid)
        return active
    except Exception as e:
        logger.error(f"Error loading active subs: {e}")
        return []

async def fetch_trade_data():
    """جلب بيانات الصفقة من بوت الإشارات"""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{SIGNALS_URL}/active_trades")
            if r.status_code == 200:
                data = r.json()
                if data:
                    # أول صفقة نشطة
                    trade = list(data.values())[0]
                    return trade
    except Exception as e:
        logger.error(f"Error fetching trade data: {e}")
    return None

def make_trade_card(trade: dict, card_type: str = "entry") -> io.BytesIO:
    """توليد كارد صورة للصفقة"""
    W, H = 800, 320

    BLACK = (0, 0, 0)
    WHITE = (255, 255, 255)
    GRAY1 = (180, 183, 190)
    GRAY2 = (100, 103, 112)
    GREEN = (0, 200, 100)
    RED   = (235, 55, 55)
    BLUE  = (80, 150, 255)
    DIV   = (35, 35, 38)

    try:
        bg = Image.open("card_bg.png").convert("RGB").resize((W, H))
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 200))
        img = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
    except:
        img = Image.new("RGB", (W, H), BLACK)

    draw = ImageDraw.Draw(img)

    bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    reg  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    try:
        f48 = ImageFont.truetype(bold, 48)
        f28 = ImageFont.truetype(bold, 28)
        f17 = ImageFont.truetype(bold, 17)
        f14 = ImageFont.truetype(reg,  14)
        f12 = ImageFont.truetype(reg,  12)
    except:
        f48 = f28 = f17 = f14 = f12 = ImageFont.load_default()

    is_put     = trade.get("type", "").upper() == "PUT"
    type_color = RED if is_put else GREEN
    entry      = float(trade.get("entry", 0))
    max_price  = float(trade.get("max_price", entry))
    symbol     = trade.get("symbol", "SPXW")
    strike     = trade.get("strike", "")
    expiry     = trade.get("expiry", "")
    opt_type   = trade.get("type", "").upper()

    # Top red/green line
    draw.rectangle([0, 0, W, 4], fill=type_color)

    # Header
    draw.rounded_rectangle([20, 14, 100, 46], radius=6, fill=(50,12,12) if is_put else (12,40,20))
    draw.text((60, 30), opt_type, fill=type_color, font=f17, anchor="mm")
    draw.text((116, 14), f"{symbol}", fill=WHITE, font=f28)
    draw.text((116, 44), f"${strike}  ·  {expiry}", fill=GRAY1, font=f12)

    # Card type label
    label = "سعر الدخول" if card_type == "entry" else "أعلى سعر"
    draw.text((W-20, 30), label, fill=GRAY2, font=f12, anchor="rm")

    draw.line([20, 68, W-20, 68], fill=DIV, width=1)

    # Price
    price = entry if card_type == "entry" else max_price
    draw.text((24, 82), f"${price:.2f}", fill=WHITE, font=f48)

    if card_type == "high":
        pnl   = (max_price - entry) * 100
        sign  = "+" if pnl >= 0 else ""
        color = GREEN if pnl >= 0 else RED
        draw.rounded_rectangle([28, 140, 220, 163], radius=5, fill=(8,40,18) if pnl>=0 else (44,8,8))
        draw.text((124, 151), f"{sign}${pnl:.0f}  ({sign}{((max_price-entry)/entry*100):.1f}%)", fill=color, font=f14, anchor="mm")

    # Bid/Ask
    draw.line([20, 178, W-20, 178], fill=DIV, width=1)
    draw.text((24, 190), "Entry", fill=GRAY2, font=f12)
    draw.text((24, 206), f"${entry:.2f}", fill=GRAY1, font=f17)
    if card_type == "high":
        draw.text((W//2, 190), "High", fill=GRAY2, font=f12, anchor="mm")
        draw.text((W//2, 206), f"${max_price:.2f}", fill=WHITE, font=f17, anchor="mm")

    # Footer
    draw.line([20, 240, W-20, 240], fill=DIV, width=1)
    draw.text((W//2, 268), datetime.now().strftime("%d %b %Y  ·  BAM Signals"), fill=GRAY2, font=f12, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def make_combined_image(trade: dict) -> io.BytesIO:
    """دمج كارد الدخول وكارد أعلى سعر في صورة واحدة"""
    card1 = make_trade_card(trade, "entry")
    card2 = make_trade_card(trade, "high")

    img1 = Image.open(card1)
    img2 = Image.open(card2)

    W  = max(img1.width, img2.width)
    H  = img1.height + img2.height + 10
    combined = Image.new("RGB", (W, H), (0, 0, 0))
    combined.paste(img1, (0, 0))
    combined.paste(img2, (0, img1.height + 10))

    buf = io.BytesIO()
    combined.save(buf, format="PNG")
    buf.seek(0)
    return buf

def build_caption(trade: dict) -> str:
    entry     = float(trade.get("entry", 0))
    max_price = float(trade.get("max_price", entry))
    pnl       = (max_price - entry) * 100
    sign      = "+" if pnl >= 0 else ""
    symbol    = trade.get("symbol", "SPXW")
    strike    = trade.get("strike", "")
    opt_type  = trade.get("type", "").upper()

    return (
        f"📊 *صفقة اليوم*\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🟢 {symbol}  |  {opt_type}  |  ${strike}\n\n"
        f"💵 سعر الدخول:   ${entry:.2f}\n"
        f"📈 أعلى سعر:     ${max_price:.2f}\n"
        f"💰 الربح:        {sign}${pnl:.0f}\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🔔 لا تفوّت الصفقة القادمة\n"
        f"[انضم الآن](https://{BOT_LINK})"
    )

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid     = update.effective_user.id
    current = get_admin()
    if current is None:
        set_admin(uid)
        await update.message.reply_text(f"✅ تم تسجيلك كأدمن!\nID: `{uid}`", parse_mode="Markdown")
    elif current == uid:
        await update.message.reply_text(f"✅ أنت الأدمن.\nID: `{uid}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("⛔ أدمن مسجّل مسبقاً.")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(get_admin()):
        await update.message.reply_text("⛔ غير مصرح.")
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 إرسال صفقة اليوم", callback_data="bc_trade")],
        [InlineKeyboardButton("📢 برودكاست عادي — كل المستخدمين", callback_data="bc_all")],
        [InlineKeyboardButton("✅ برودكاست — المشتركين فقط", callback_data="bc_active")],
        [InlineKeyboardButton("📣 برودكاست — القناة العامة فقط", callback_data="bc_channel")],
        [InlineKeyboardButton("🔥 برودكاست — الكل", callback_data="bc_full")],
    ])
    await update.message.reply_text(
        "📤 *إرسال برودكاست*\n\nاختر نوع البرودكاست:",
        parse_mode="Markdown",
        reply_markup=kb
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    if str(query.from_user.id) != str(get_admin()):
        await query.answer("⛔ غير مصرح", show_alert=True)
        return

    # ── صفقة اليوم ──
    if data == "bc_trade":
        await query.edit_message_text("⏳ جاري جلب بيانات الصفقة...")
        trade = await fetch_trade_data()
        if not trade:
            await query.edit_message_text(
                "⚠️ لا توجد صفقات نشطة في بوت الإشارات.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]])
            )
            return

        # معاينة
        combined = make_combined_image(trade)
        caption  = build_caption(trade)
        await query.message.reply_photo(
            photo=combined,
            caption=caption + "\n\n_معاينة — لم يُرسَل بعد_",
            parse_mode="Markdown"
        )
        context.user_data["trade_data"] = trade
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ إرسال للقناة", callback_data="trade_confirm"),
            InlineKeyboardButton("❌ إلغاء", callback_data="trade_cancel"),
        ]])
        await query.message.reply_text("هل تريد إرسال صفقة اليوم للقناة العامة؟", reply_markup=kb)
        return

    # ── تأكيد إرسال الصفقة ──
    if data == "trade_confirm":
        trade = context.user_data.get("trade_data")
        if not trade:
            await query.edit_message_text("⚠️ خطأ، حاول مجدداً.")
            return
        await query.edit_message_text("⏳ جاري الإرسال...")
        combined = make_combined_image(trade)
        caption  = build_caption(trade)
        try:
            await context.bot.send_photo(
                chat_id=PUBLIC_CHANNEL,
                photo=combined,
                caption=caption,
                parse_mode="Markdown"
            )
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="✅ تم إرسال صفقة اليوم للقناة العامة!"
            )
        except Exception as e:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ فشل الإرسال: {e}"
            )
        context.user_data.clear()
        return

    if data == "trade_cancel":
        context.user_data.clear()
        await query.edit_message_text("❌ تم الإلغاء.")
        return

    # ── برودكاست عادي ──
    targets = {"bc_all": "all", "bc_active": "active", "bc_channel": "channel", "bc_full": "full"}
    target  = targets.get(data)
    if target:
        context.user_data["bc_target"]       = target
        context.user_data["awaiting_bc_msg"] = True
        labels = {"all": "كل المستخدمين", "active": "المشتركين النشطين", "channel": "القناة العامة فقط", "full": "الكل"}
        await query.edit_message_text(
            f"✅ الجمهور: *{labels[target]}*\n\n"
            f"أرسل الرسالة الآن (نص، صورة، فيديو)\n\nللإلغاء: /cancel",
            parse_mode="Markdown"
        )

async def receive_broadcast_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(get_admin()):
        return
    if not context.user_data.get("awaiting_bc_msg"):
        return
    target = context.user_data.get("bc_target", "all")
    context.user_data["awaiting_bc_msg"] = False
    context.user_data["bc_message"] = {
        "message_id": update.message.message_id,
        "chat_id":    update.effective_chat.id,
        "target":     target,
    }
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ إرسال", callback_data="bc_confirm"),
        InlineKeyboardButton("❌ إلغاء", callback_data="bc_cancel"),
    ]])
    await update.message.reply_text("👆 معاينة رسالتك.\n\nهل تريد إرسالها؟", reply_markup=kb)

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "bc_cancel":
        context.user_data.clear()
        await query.edit_message_text("❌ تم الإلغاء.")
        return
    if str(query.from_user.id) != str(get_admin()):
        return
    bc_msg = context.user_data.get("bc_message")
    if not bc_msg:
        await query.edit_message_text("⚠️ خطأ، حاول مجدداً.")
        return
    target     = bc_msg["target"]
    src_chat   = bc_msg["chat_id"]
    src_msg_id = bc_msg["message_id"]
    await query.edit_message_text("⏳ جاري الإرسال...")
    sent_ok = sent_err = 0
    user_ids = []
    if target in ("all", "full"):
        user_ids = get_all_users()
    elif target == "active":
        user_ids = get_active_subscribers()
    for uid in user_ids:
        try:
            await context.bot.copy_message(chat_id=int(uid), from_chat_id=src_chat, message_id=src_msg_id)
            sent_ok += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            sent_err += 1
            logger.error(f"BC error to {uid}: {e}")
    channel_ok = False
    if target in ("channel", "full"):
        try:
            await context.bot.copy_message(chat_id=PUBLIC_CHANNEL, from_chat_id=src_chat, message_id=src_msg_id)
            channel_ok = True
        except Exception as e:
            logger.error(f"BC channel error: {e}")
    db = load_broadcast_db()
    db["stats"].append({"target": target, "sent_ok": sent_ok, "sent_err": sent_err, "channel": channel_ok, "sent_at": datetime.now().isoformat()})
    save_broadcast_db(db)
    summary = f"✅ *تم الإرسال!*\n\n👥 المستخدمين: {sent_ok} نجح | {sent_err} فشل\n"
    if target in ("channel", "full"):
        summary += f"📣 القناة العامة: {'✅' if channel_ok else '❌'}\n"
    await context.bot.send_message(chat_id=query.message.chat_id, text=summary, parse_mode="Markdown")
    context.user_data.clear()

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ تم الإلغاء.")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(get_admin()):
        return
    all_users    = get_all_users()
    active_users = get_active_subscribers()
    db           = load_broadcast_db()
    stats        = db.get("stats", [])
    text = (
        f"📊 *إحصائيات البرودكاست*\n\n"
        f"👥 إجمالي المستخدمين: {len(all_users)}\n"
        f"✅ المشتركين النشطين: {len(active_users)}\n"
        f"📤 عدد البرودكاستات: {len(stats)}\n"
    )
    if stats:
        last = stats[-1]
        text += f"\n*آخر برودكاست:*\n• الوقت: {last['sent_at'][:16]}\n• نجح: {last['sent_ok']} | فشل: {last['sent_err']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("admin",     admin_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("stats",     stats_cmd))
    app.add_handler(CommandHandler("cancel",    cancel_cmd))
    app.add_handler(CallbackQueryHandler(button_handler,    pattern="^(bc_trade|bc_all|bc_active|bc_channel|bc_full|trade_confirm|trade_cancel|back_main)$"))
    app.add_handler(CallbackQueryHandler(confirm_broadcast, pattern="^bc_(confirm|cancel)$"))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, receive_broadcast_msg))
    print("Broadcast bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
