import random
import logging
from datetime import date
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import Forbidden, BadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from config import TZ, USERS, SCHEDULE
from database import get_all_registered_users
from messages.public_pools import POOLS, SLOT_CATEGORY, SCHEDULE_SLOTS

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=TZ)

_POSITIVE_BUTTONS = [
    "❤️", "💪 Я СМОГУ!", "🔥 ПОЛНЫЙ ГАЗ", "🚀 ДАВАЙ ДАВАЙ",
    "💥 Я СИЛАЧ", "⚡️ ЗАРЯЖЕН", "🏆 Я ЧЕМПИОН", "🌟 Я ЗВЕЗДА",
    "💎 Я МОЛОДЕЦ", "🎯 В ТОЧКУ", "❤️‍🔥 ГОРЮ", "😎 Я КРАСАВЧИК",
    "💪 НЕ СДАМСЯ", "🚀 ВЗЛЕТАЮ", "🌋 ВЗРЫВАЮСЬ", "🏅 Я ПОБЕДИЛ",
    "🎉 УРАААА", "✊ Я ДЕРЖУСЬ", "🦁 Я ЛЕВ", "🐉 Я ДРАКОН",
    "💫 Я В ПОТОКЕ", "🎸 Я РОКЕР", "🔑 Я ОТКРЫВАЮ ДВЕРИ",
]

_MEH_BUTTONS = ["Я ГРИНЧ 🫠", "Я КАКАШКА 💩"]

_CAT_CAPTIONS = [
    "Доброе утро! ☀️ Этот котик верит в тебя!",
    "Вставай, этот красавец уже ждёт! 🐱☀️",
    "Утро! Котик прислал тебе свою энергию на весь день 🐱🔥",
    "С добрым утром! Смотри какой красавец — ты сегодня такой же! 🐱",
    "Доброе утро! Котик сказал — сегодня будет огонь! 🐱💪",
    "Доброе утро! 🐱 Этот кот не сдаётся — и ты не сдашься!",
    "Доброе утро! Мир ждёт тебя, и котик тоже 🐱☀️",
]


def _cycle_pick(items: list, user_id: int, slot_idx: int = 0) -> str:
    """Pick from list using day+user hash to cycle without repeating."""
    day = date.today().timetuple().tm_yday
    idx = (day * 7 + abs(user_id) % 1000 * 13 + slot_idx) % len(items)
    return items[idx]


def _reaction_keyboard(user_id: int, slot_idx: int) -> InlineKeyboardMarkup:
    positive = _POSITIVE_BUTTONS[slot_idx % len(_POSITIVE_BUTTONS)]
    meh = _MEH_BUTTONS[slot_idx % len(_MEH_BUTTONS)]
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(positive, callback_data=f"ack_{user_id}"),
        InlineKeyboardButton(meh,      callback_data=f"meh_{user_id}"),
    ]])


async def send_morning_cat(bot: Bot, user_id: int, name: str) -> None:
    caption = random.choice(_CAT_CAPTIONS)
    try:
        await bot.send_photo(
            chat_id=user_id,
            photo="https://cataas.com/cat",
            caption=caption,
        )
        logger.info(f"Morning cat sent to {name} ({user_id}) ✓")
    except Exception as e:
        logger.warning(f"Morning cat failed for {name} ({user_id}): {e}")


async def send_scheduled_message(bot: Bot, user_id: int, texts: list[str], slot_idx: int = 0) -> None:
    """Send a message from the hardcoded config pool (existing friends)."""
    user = USERS.get(user_id, {})
    nick = user.get("nick", "")
    name = user.get("name", str(user_id))

    text = _cycle_pick(texts, user_id, slot_idx)
    full_text = f"{nick}\n\n{text}" if nick else text

    try:
        await bot.send_message(
            chat_id=user_id,
            text=full_text,
            reply_markup=_reaction_keyboard(user_id, slot_idx),
        )
        logger.info(f"Sent to {name} ({user_id}) ✓")
    except Forbidden:
        logger.warning(f"{name} ({user_id}) BLOCKED")
    except BadRequest as e:
        logger.error(f"{name} ({user_id}) FAILED — {e}")


async def send_registered_message(bot: Bot, user_data: dict, time_str: str, slot_idx: int = 0) -> None:
    """Send a message from the generic pool (self-registered users)."""
    if user_data.get("paused"):
        return

    telegram_id = user_data["telegram_id"]
    name = user_data["name"]
    nick = user_data.get("nick", "")
    gender = user_data["gender"]
    style = user_data["style"]

    category = SLOT_CATEGORY.get(time_str, "midday")
    pool = POOLS.get((gender, style), {}).get(category, [])

    if not pool:
        logger.warning(f"No pool for ({gender}, {style}, {category})")
        return

    text = _cycle_pick(pool, telegram_id, slot_idx)
    full_text = f"{nick}\n\n{text}" if nick else text

    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=full_text,
            reply_markup=_reaction_keyboard(telegram_id, slot_idx),
        )
        logger.info(f"Sent to {name} ({telegram_id}) [registered] ✓")
    except Forbidden:
        logger.warning(f"{name} ({telegram_id}) BLOCKED")
    except BadRequest as e:
        logger.error(f"{name} ({telegram_id}) FAILED — {e}")


def schedule_registered_user_jobs(bot: Bot, user_data: dict) -> int:
    """Add APScheduler jobs for one registered user. Returns job count added."""
    telegram_id = user_data["telegram_id"]
    name = user_data["name"]
    schedule_type = user_data.get("schedule_type", "rare")
    times = SCHEDULE_SLOTS.get(schedule_type, SCHEDULE_SLOTS["rare"])
    count = 0

    for slot_idx, time_str in enumerate(times):
        hour, minute = map(int, time_str.split(":"))
        job_id = f"reg_{telegram_id}_{time_str.replace(':', '')}"

        scheduler.add_job(
            send_registered_message,
            CronTrigger(hour=hour, minute=minute, timezone=TZ),
            args=[bot, user_data, time_str, slot_idx],
            id=job_id,
            replace_existing=True,
            misfire_grace_time=120,
            name=f"{name} | {time_str} [reg]",
        )
        count += 1

    logger.info(f"Scheduled {count} jobs for registered user {name} ({telegram_id})")
    return count


def setup_jobs(bot: Bot) -> None:
    job_count = 0

    # Morning cat at 07:00 for all hardcoded friends
    for user_id, info in USERS.items():
        name = info.get("name", str(user_id))
        scheduler.add_job(
            send_morning_cat,
            CronTrigger(hour=7, minute=0, timezone=TZ),
            args=[bot, user_id, name],
            id=f"cat_{user_id}",
            replace_existing=True,
            misfire_grace_time=120,
            name=f"{name} | 07:00 [котик]",
        )
        job_count += 1

    # Hardcoded friends scheduled messages
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

    # Self-registered users from Supabase
    registered = get_all_registered_users()
    for user_data in registered:
        if not user_data.get("paused"):
            job_count += schedule_registered_user_jobs(bot, user_data)

    logger.info(f"Jobs scheduled: {job_count} total ({len(registered)} registered users)")
