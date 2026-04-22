import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import Forbidden
from config import ADMIN_ID, USERS
from scheduler import scheduler, send_scheduled_message
from messages.pools import MESSAGES

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
        f"Твой ID: <code>{user.id}</code>\n\n"
        f"Жди сообщений по расписанию. 🔥",
        parse_mode="HTML",
    )
    logger.info(f"New /start: {user.full_name} ({user.id})")


@admin_only
async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    jobs = scheduler.get_jobs()
    if not jobs:
        await update.message.reply_text("Нет активных задач в планировщике.")
        return

    lines = [f"<b>Активные задачи ({len(jobs)}):</b>\n"]
    for job in sorted(jobs, key=lambda j: j.next_run_time or 0):
        next_run = job.next_run_time.strftime("%d.%m %H:%M МСК") if job.next_run_time else "—"
        lines.append(f"• <code>{job.name}</code>\n  ➜ {next_run}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


@admin_only
async def sendnow_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /sendnow <phase> — немедленно отправить сообщение указанной фазы всем пользователям.
    Пример: /sendnow morning
    """
    if not context.args:
        await update.message.reply_text(
            "Использование: /sendnow <morning|day|evening>\n"
            "Пример: /sendnow morning"
        )
        return

    phase = context.args[0].lower()
    if phase not in MESSAGES:
        await update.message.reply_text("Неверная фаза. Доступны: morning, day, evening")
        return

    if not USERS:
        await update.message.reply_text("Список пользователей пуст. Добавь друзей в config.py")
        return

    bot = context.bot
    sent = 0
    for user_id in USERS:
        await send_scheduled_message(bot, user_id, phase)
        sent += 1

    await update.message.reply_text(
        f"Отправлено: {sent} из {len(USERS)} пользователей\nФаза: <b>{phase}</b>",
        parse_mode="HTML",
    )


@admin_only
async def broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /broadcast <текст> — отправить произвольный текст всем пользователям.
    Пример: /broadcast Сегодня собираемся в 19:00, не забудьте.
    """
    if not context.args:
        await update.message.reply_text("Использование: /broadcast <текст>")
        return

    if not USERS:
        await update.message.reply_text("Список пользователей пуст. Добавь друзей в config.py")
        return

    text = " ".join(context.args)
    bot = context.bot
    sent = 0
    blocked = 0

    for user_id, name in USERS.items():
        try:
            await bot.send_message(chat_id=user_id, text=text)
            sent += 1
        except Forbidden:
            logger.warning(f"Broadcast BLOCKED: {name} ({user_id})")
            blocked += 1

    result = f"Рассылка завершена.\nОтправлено: {sent}/{len(USERS)}"
    if blocked:
        result += f"\nЗаблокировали бота: {blocked}"
    await update.message.reply_text(result)
