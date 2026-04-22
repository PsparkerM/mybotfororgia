import random
import logging
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import Forbidden, BadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from config import TZ, USERS, SCHEDULE

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=TZ)


_POSITIVE = ["❤️", "ПОЛНЫЙ ГАЗ СУКА", "😘"]


def _reaction_keyboard(user_id: int, slot_idx: int) -> InlineKeyboardMarkup:
    positive = _POSITIVE[slot_idx % len(_POSITIVE)]
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(positive,             callback_data=f"ack_{user_id}"),
        InlineKeyboardButton("Я УНЫЛОЕ ГАВНО",    callback_data=f"meh_{user_id}"),
    ]])


async def send_scheduled_message(bot: Bot, user_id: int, texts: list[str], slot_idx: int = 0) -> None:
    user = USERS.get(user_id, {})
    nick = user.get("nick", "")
    name = user.get("name", str(user_id))

    text = random.choice(texts)
    full_text = f"{nick}\n\n{text}" if nick else text

    try:
        await bot.send_message(
            chat_id=user_id,
            text=full_text,
            reply_markup=_reaction_keyboard(user_id, slot_idx),
        )
        logger.info(f"Sent to {name} ({user_id}) ✓")
    except Forbidden:
        logger.warning(f"{name} ({user_id}) BLOCKED — пользователь заблокировал бота")
    except BadRequest as e:
        logger.error(f"{name} ({user_id}) FAILED — {e}")


def setup_jobs(bot: Bot) -> None:
    job_count = 0

    for user_id, slots in SCHEDULE.items():
        name = USERS.get(user_id, {}).get("name", str(user_id))

        for slot_idx, slot in enumerate(slots):
            time_str = slot["time"]
            texts = slot["texts"]
            hour, minute = map(int, time_str.split(":"))
            job_id = f"{user_id}_{time_str.replace(':', '')}"

            scheduler.add_job(
                send_scheduled_message,
                CronTrigger(hour=hour, minute=minute, timezone=TZ),
                args=[bot, user_id, texts, slot_idx],
                id=job_id,
                replace_existing=True,
                misfire_grace_time=120,
                name=f"{name} | {time_str}",
            )
            job_count += 1

    logger.info(f"Jobs scheduled: {job_count} total")
