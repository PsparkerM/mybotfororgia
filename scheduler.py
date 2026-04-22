import logging
from telegram import Bot
from telegram.error import Forbidden, BadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from config import TZ, USERS, SCHEDULE

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=TZ)


async def send_scheduled_message(bot: Bot, user_id: int, text: str) -> None:
    user = USERS.get(user_id, {})
    nick = user.get("nick", "")
    name = user.get("name", str(user_id))

    full_text = f"{nick}\n\n{text}" if nick else text

    try:
        await bot.send_message(chat_id=user_id, text=full_text)
        logger.info(f"Sent to {name} ({user_id}) ✓")
    except Forbidden:
        logger.warning(f"{name} ({user_id}) BLOCKED — пользователь заблокировал бота")
    except BadRequest as e:
        logger.error(f"{name} ({user_id}) FAILED — {e}")


def setup_jobs(bot: Bot) -> None:
    job_count = 0

    for user_id, slots in SCHEDULE.items():
        name = USERS.get(user_id, {}).get("name", str(user_id))

        for slot in slots:
            time_str = slot["time"]
            text = slot["text"]
            hour, minute = map(int, time_str.split(":"))
            job_id = f"{user_id}_{time_str.replace(':', '')}"

            scheduler.add_job(
                send_scheduled_message,
                CronTrigger(hour=hour, minute=minute, timezone=TZ),
                args=[bot, user_id, text],
                id=job_id,
                replace_existing=True,
                misfire_grace_time=120,
                name=f"{name} | {time_str}",
            )
            job_count += 1

    logger.info(f"Jobs scheduled: {job_count} total")
