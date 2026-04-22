import os
import json
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN  = os.environ["BROADCAST_TOKEN"]
SUBSCRIBERS_DB  = "db.json"
BROADCAST_DB    = "broadcast_db.json"
PUBLIC_CHANNEL  = -1001934800979

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
        db = load_subs_db()
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
        db = load_subs_db()
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
        [InlineKeyboardButton("📢 كل المستخدمين", callback_data="bc_all")],
        [InlineKeyboardButton("✅ المشتركين النشطين فقط", callback_data="bc_active")],
        [InlineKeyboardButton("📣 القناة العامة فقط", callback_data="bc_channel")],
        [InlineKeyboardButton("🔥 الكل (مستخدمين + قناة)", callback_data="bc_full")],
    ])
    await update.message.reply_text(
        "📤 *إرسال برودكاست*\n\nاختر الجمهور المستهدف:",
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
    targets = {"bc_all": "all", "bc_active": "active", "bc_channel": "channel", "bc_full": "full"}
    target  = targets.get(data, "all")
    context.user_data["bc_target"]       = target
    context.user_data["awaiting_bc_msg"] = True
    labels = {"all": "كل المستخدمين", "active": "المشتركين النشطين", "channel": "القناة العامة فقط", "full": "الكل (مستخدمين + قناة)"}
    await query.edit_message_text(
        f"✅ الجمهور: *{labels[target]}*\n\n"
        f"أرسل الرسالة الآن (نص، صورة، فيديو، صوت)\n\n"
        f"للإلغاء: /cancel",
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
    summary = f"✅ *تم إرسال البرودكاست!*\n\n👥 المستخدمين: {sent_ok} نجح | {sent_err} فشل\n"
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
    app.add_handler(CallbackQueryHandler(button_handler,    pattern="^bc_(all|active|channel|full)$"))
    app.add_handler(CallbackQueryHandler(confirm_broadcast, pattern="^bc_(confirm|cancel)$"))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, receive_broadcast_msg))
    print("Broadcast bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
