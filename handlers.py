import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import Forbidden
from config import ADMIN_ID, USERS, SCHEDULE
from scheduler import scheduler, send_scheduled_message

logger = logging.getLogger(__name__)


def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            return
        return await func(update, context)
    return wrapper


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! Бот активирован.\n"
        f"Твой ID: <code>{user.id}</code>",
        parse_mode="HTML",
    )
    logger.info(f"/start: {user.full_name} ({user.id})")


@admin_only
async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    jobs = scheduler.get_jobs()
    if not jobs:
        await update.message.reply_text("Нет активных задач.")
        return

    lines = [f"<b>Задачи ({len(jobs)}):</b>\n"]
    for job in sorted(jobs, key=lambda j: j.next_run_time or 0):
        next_run = job.next_run_time.strftime("%d.%m %H:%M МСК") if job.next_run_time else "—"
        lines.append(f"• {job.name} → {next_run}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


@admin_only
async def sendnow_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /sendnow <user_id> <HH:MM> — отправить конкретный слот прямо сейчас.
    /sendnow all <HH:MM>       — отправить слот всем пользователям у кого он есть.
    Пример: /sendnow 1199979214 09:00
    Пример: /sendnow all 09:00
    """
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Использование:\n"
            "/sendnow <user_id> <HH:MM>\n"
            "/sendnow all <HH:MM>"
        )
        return

    target, time_str = args[0], args[1]
    bot = context.bot
    sent = 0

    if target == "all":
        for user_id, slots in SCHEDULE.items():
            for slot in slots:
                if slot["time"] == time_str:
                    await send_scheduled_message(bot, user_id, slot["text"])
                    sent += 1
    else:
        try:
            user_id = int(target)
        except ValueError:
            await update.message.reply_text("Неверный user_id")
            return

        slots = SCHEDULE.get(user_id, [])
        for slot in slots:
            if slot["time"] == time_str:
                await send_scheduled_message(bot, user_id, slot["text"])
                sent += 1

    if sent:
        await update.message.reply_text(f"Отправлено: {sent} сообщений ({time_str})")
    else:
        await update.message.reply_text(f"Слот {time_str} не найден")


@admin_only
async def dm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /dm <user_id> <текст> — отправить произвольный текст одному пользователю.
    Пример: /dm 892217528 Майя, ты молодец!
    """
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Использование: /dm <user_id> <текст>")
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Неверный user_id")
        return

    text = " ".join(context.args[1:])
    try:
        await context.bot.send_message(chat_id=user_id, text=text)
        name = USERS.get(user_id, {}).get("name", str(user_id))
        await update.message.reply_text(f"Отправлено → {name}")
    except Forbidden:
        await update.message.reply_text("Пользователь заблокировал бота")


@admin_only
async def broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /broadcast <текст> — отправить произвольный текст всем пользователям.
    """
    if not context.args:
        await update.message.reply_text("Использование: /broadcast <текст>")
        return

    text = " ".join(context.args)
    bot = context.bot
    sent, blocked = 0, 0

    for user_id, info in USERS.items():
        try:
            await bot.send_message(chat_id=user_id, text=text)
            sent += 1
        except Forbidden:
            logger.warning(f"Broadcast BLOCKED: {info['name']} ({user_id})")
            blocked += 1

    result = f"Рассылка завершена.\nОтправлено: {sent}/{len(USERS)}"
    if blocked:
        result += f"\nЗаблокировали бота: {blocked}"
    await update.message.reply_text(result)
