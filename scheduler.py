import logging
import random
from telegram import Bot
from telegram.error import Forbidden, BadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from config import TZ, USERS, SCHEDULE
from messages.pools import MESSAGES

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=TZ)


async def send_scheduled_message(bot: Bot, user_id: int, phase: str) -> None:
    pool = MESSAGES.get(phase, [])
    if not pool:
        logger.warning(f"Empty message pool for phase '{phase}'")
        return

    text = random.choice(pool)
    name = USERS.get(user_id, str(user_id))

    try:
        await bot.send_message(chat_id=user_id, text=text)
        logger.info(f"[{phase.upper()}] → {name} ({user_id}) ✓")
    except Forbidden:
        logger.warning(f"[{phase.upper()}] → {name} ({user_id}) BLOCKED — пользователь заблокировал бота")
    except BadRequest as e:
        logger.error(f"[{phase.upper()}] → {name} ({user_id}) FAILED — {e}")


def setup_jobs(bot: Bot) -> None:
    job_count = 0

    for user_id, phases in SCHEDULE.items():
        for phase, time_str in phases.items():
            hour, minute = map(int, time_str.split(":"))
            name = USERS.get(user_id, str(user_id))

            scheduler.add_job(
                send_scheduled_message,
                CronTrigger(hour=hour, minute=minute, timezone=TZ),
                args=[bot, user_id, phase],
                id=f"{user_id}_{phase}",
                replace_existing=True,
                misfire_grace_time=120,
                name=f"{name} | {phase} | {time_str}",
            )
            job_count += 1

    logger.info(f"Jobs scheduled: {job_count} total")
