import random
import logging
from functools import wraps
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import Forbidden, BadRequest
from config import ADMIN_ID, USERS, SCHEDULE
from database import get_user, create_user, increment_meh, resume_user, get_all_registered_users
from messages.public_pools import EXPLOSIVE_REACTIONS, WELCOME
from scheduler import scheduler, send_scheduled_message, schedule_registered_user_jobs

logger = logging.getLogger(__name__)

# ConversationHandler states
GENDER, NAME, STYLE, SCHEDULE_TYPE = range(4)


def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            return
        return await func(update, context)
    return wrapper


# ── Onboarding ────────────────────────────────────────────────────────────────

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user

    # Existing hardcoded friend
    if user.id in USERS:
        info = USERS[user.id]
        await update.message.reply_text(
            f"Привет, {info['name']}! Бот активирован. 🔥\n"
            f"Твой ID: <code>{user.id}</code>",
            parse_mode="HTML",
        )
        logger.info(f"/start: {user.full_name} ({user.id}) [hardcoded]")
        return ConversationHandler.END

    # Already registered in DB
    db_user = get_user(user.id)
    if db_user:
        status = "⏸ Мотивация на паузе." if db_user.get("paused") else "Мотивация идёт в штатном режиме! 🔥"
        await update.message.reply_text(
            f"Привет снова, {db_user['name']}! Ты уже в системе.\n"
            f"{status}\n\n"
            f"Твой ID: <code>{user.id}</code>",
            parse_mode="HTML",
        )
        logger.info(f"/start: {user.full_name} ({user.id}) [already registered]")
        return ConversationHandler.END

    # New user — start onboarding
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Мужчина 💪", callback_data="reg_gender_male"),
        InlineKeyboardButton("Девушка 🌸", callback_data="reg_gender_female"),
    ]])
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я бот-мотиватор. Каждый день буду присылать тебе заряд мотивации "
        "прямо в Telegram — никаких лишних слов, только огонь.\n\n"
        "Для начала — кто ты?",
        reply_markup=keyboard,
    )
    logger.info(f"/start: {user.full_name} ({user.id}) [new user, onboarding]")
    return GENDER


async def gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    gender = query.data.replace("reg_gender_", "")
    context.user_data["gender"] = gender

    label = "Мужчина 💪" if gender == "male" else "Девушка 🌸"
    await query.edit_message_text(
        f"Отлично, {label}!\n\nКак тебя звать? Напиши имя или прозвище:",
    )
    return NAME


async def name_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if not name or len(name) > 50:
        await update.message.reply_text("Слишком длинное или пустое имя. Попробуй ещё раз:")
        return NAME

    context.user_data["name"] = name

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Жёстко с юмором", callback_data="reg_style_harsh")],
        [InlineKeyboardButton("🌸 Нежно и поддерживающе", callback_data="reg_style_gentle")],
        [InlineKeyboardButton("💪 Всё и сразу", callback_data="reg_style_mixed")],
    ])
    await update.message.reply_text(
        f"Отлично, {name}! 👊\n\nКак тебя мотивировать?",
        reply_markup=keyboard,
    )
    return STYLE


async def style_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    style = query.data.replace("reg_style_", "")
    context.user_data["style"] = style

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Часто (6 раз в день)", callback_data="reg_sched_often")],
        [InlineKeyboardButton("☀️ 3 раза: утро / обед / вечер", callback_data="reg_sched_rare")],
    ])
    await query.edit_message_text(
        "Как часто присылать мотивацию?",
        reply_markup=keyboard,
    )
    return SCHEDULE_TYPE


async def schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user = query.from_user
    schedule_type = query.data.replace("reg_sched_", "")

    # Guard: user_data can be lost if bot restarted mid-conversation
    gender = context.user_data.get("gender")
    style = context.user_data.get("style")
    name = context.user_data.get("name")

    if not gender or not style or not name:
        logger.warning(f"schedule_callback: user_data lost for {user.id}. Starting over.")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Мужчина 💪", callback_data="reg_gender_male"),
            InlineKeyboardButton("Девушка 🌸", callback_data="reg_gender_female"),
        ]])
        await query.edit_message_text(
            "Бот перезапускался и данные потерялись. Давай начнём заново — кто ты?",
            reply_markup=keyboard,
        )
        return GENDER

    # Save to Supabase
    logger.info(f"Registering user {user.id}: name={name}, gender={gender}, style={style}, sched={schedule_type}")
    user_data = create_user(
        telegram_id=user.id,
        name=name,
        nick="",
        gender=gender,
        style=style,
        schedule_type=schedule_type,
    )

    if not user_data:
        await query.edit_message_text(
            "⚠️ Не удалось сохранить данные. Скорее всего, таблица в базе данных ещё не создана.\n\n"
            "Попробуй через /start чуть позже — администратор уже в курсе."
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка регистрации пользователя!\n"
                 f"ID: <code>{user.id}</code>, имя: {name}\n"
                 f"Проверь Railway логи и убедись что таблица registered_users создана в Supabase.",
            parse_mode="HTML",
        )
        return ConversationHandler.END

    # Schedule jobs immediately
    schedule_registered_user_jobs(context.bot, user_data)

    welcome = WELCOME.get((gender, style), "Добро пожаловать! Мотивация уже в пути! 🔥")
    freq_label = "6 раз в день" if schedule_type == "often" else "утром, в обед и вечером"

    await query.edit_message_text(
        f"Готово, {name}! ✅\n\n"
        f"{welcome}\n\n"
        f"📅 Буду писать тебе {freq_label}.\n\n"
        f"Твой ID (на всякий случай): <code>{user.id}</code>",
        parse_mode="HTML",
    )

    # Notify admin
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"🆕 Новый пользователь зарегистрировался!\n\n"
            f"Имя: <b>{name}</b>\n"
            f"Пол: {'Мужчина' if gender == 'male' else 'Девушка'}\n"
            f"Стиль: {style}\n"
            f"Расписание: {schedule_type}\n"
            f"ID: <code>{user.id}</code>"
        ),
        parse_mode="HTML",
    )

    logger.info(f"New user registered: {name} ({user.id}), gender={gender}, style={style}, sched={schedule_type}")
    return ConversationHandler.END


# ── Admin commands ────────────────────────────────────────────────────────────

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
            for slot_idx, slot in enumerate(slots):
                if slot["time"] == time_str:
                    await send_scheduled_message(bot, user_id, slot["texts"], slot_idx)
                    sent += 1
    else:
        try:
            user_id = int(target)
        except ValueError:
            await update.message.reply_text("Неверный user_id")
            return

        slots = SCHEDULE.get(user_id, [])
        for slot_idx, slot in enumerate(slots):
            if slot["time"] == time_str:
                await send_scheduled_message(bot, user_id, slot["texts"], slot_idx)
                sent += 1

    if sent:
        await update.message.reply_text(f"Отправлено: {sent} сообщений ({time_str})")
    else:
        await update.message.reply_text(f"Слот {time_str} не найден")


@admin_only
async def dm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /dm <user_id> <текст> — отправить произвольный текст одному пользователю.
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
        if not name:
            db_user = get_user(user_id)
            name = db_user["name"] if db_user else str(user_id)
        await update.message.reply_text(f"Отправлено → {name}")
    except Forbidden:
        await update.message.reply_text("Пользователь заблокировал бота")
    except BadRequest as e:
        await update.message.reply_text(
            f"Не удалось отправить: {e}\n\nПользователь должен сначала написать /start боту"
        )


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


@admin_only
async def testdb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /testdb — проверить соединение с Supabase.
    """
    from database import get_db
    try:
        res = get_db().table("registered_users").select("telegram_id").limit(1).execute()
        count = len(get_db().table("registered_users").select("telegram_id").execute().data or [])
        await update.message.reply_text(
            f"✅ Supabase подключён.\n"
            f"Таблица registered_users: OK\n"
            f"Записей: {count}"
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка подключения к Supabase:\n<code>{type(e).__name__}: {e}</code>",
            parse_mode="HTML",
        )
        logger.error(f"testdb failed: {e}", exc_info=True)


@admin_only
async def restart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /restart <user_id> — сбросить счётчик уныния и возобновить мотивацию для пользователя.
    """
    if not context.args:
        await update.message.reply_text("Использование: /restart <user_id>")
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Неверный user_id")
        return

    db_user = get_user(user_id)
    if not db_user:
        await update.message.reply_text("Пользователь не найден в базе данных")
        return

    resume_user(user_id)
    schedule_registered_user_jobs(context.bot, db_user)

    name = db_user["name"]
    await update.message.reply_text(f"✅ {name} ({user_id}) — мотивация возобновлена, счётчик сброшен.")

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="🔄 Твоя мотивация возобновлена! Добро пожаловать обратно. Погнали! 🔥",
        )
    except (Forbidden, BadRequest):
        pass


@admin_only
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Статус задач", callback_data="menu_status")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="menu_users")],
        [InlineKeyboardButton("❌ Закрыть", callback_data="menu_close")],
    ])
    await update.message.reply_text("Меню администратора:", reply_markup=keyboard)


# ── Message forwarding ────────────────────────────────────────────────────────

async def user_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id == ADMIN_ID:
        return

    config_user = USERS.get(user.id, {})
    name = config_user.get("name") if config_user else None
    if not name:
        db_user = get_user(user.id)
        name = db_user["name"] if db_user else user.full_name

    text = update.message.text
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"💬 <b>{name}</b> написал(а):\n\n{text}",
        parse_mode="HTML",
    )


# ── Callback handlers ─────────────────────────────────────────────────────────

async def reaction_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    config_user = USERS.get(user_id, {})
    name = config_user.get("name") if config_user else None
    if not name:
        db_user = get_user(user_id)
        name = db_user["name"] if db_user else str(user_id)

    button_text = query.message.reply_markup.inline_keyboard[0][0].text

    await query.answer("🔥")
    await query.edit_message_reply_markup(reply_markup=None)

    # Explosive response to user
    explosion = random.choice(EXPLOSIVE_REACTIONS)
    await context.bot.send_message(chat_id=user_id, text=explosion)

    # Notify admin
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"{button_text} — {name} отреагировал(а)! 🔥"
    )
    logger.info(f"Positive reaction from {name} ({user_id}): {button_text}")


async def meh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    config_user = USERS.get(user_id, {})
    name = config_user.get("name") if config_user else None
    if not name:
        db_user = get_user(user_id)
        name = db_user["name"] if db_user else str(user_id)

    await query.answer("😔")
    await query.edit_message_reply_markup(reply_markup=None)

    # Track meh for registered users only
    if user_id not in USERS:
        new_count = increment_meh(user_id)
        remaining = max(0, 9 - new_count)

        if new_count >= 9:
            # Paused
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "💀 Ты истратил(а) все 9 жизней уныния.\n\n"
                    "Мотивационные сообщения приостановлены.\n"
                    "Когда будешь готов(а) вернуться — просто напиши мне, "
                    "я передам администратору."
                ),
            )
            logger.info(f"User {name} ({user_id}) PAUSED after 9 meh presses")
        else:
            # Show remaining lives
            hearts = "🫀" * remaining + "🖤" * (9 - remaining)
            await context.bot.send_message(
                chat_id=user_id,
                text=f"😔 Понимаю... Бывает.\n\n{hearts}\nЖизней осталось: {remaining}/9",
            )
    else:
        # Hardcoded friend — just notify admin
        pass

    # Notify admin
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"💀 {name} нажал(а) «Я УНЫЛОЕ ГАВНО»"
    )
    logger.info(f"Meh reaction from {name} ({user_id})")


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("Нет доступа")
        return

    action = query.data

    if action == "menu_status":
        await query.answer()
        jobs = scheduler.get_jobs()
        if not jobs:
            text = "Нет активных задач."
        else:
            lines = [f"<b>Задачи ({len(jobs)}):</b>\n"]
            for job in sorted(jobs, key=lambda j: j.next_run_time or 0):
                next_run = job.next_run_time.strftime("%d.%m %H:%M МСК") if job.next_run_time else "—"
                lines.append(f"• {job.name} → {next_run}")
            text = "\n".join(lines)
        await query.edit_message_text(text, parse_mode="HTML")

    elif action == "menu_users":
        await query.answer()
        lines = ["<b>Пользователи (конфиг):</b>\n"]
        for uid, info in USERS.items():
            slot_count = len(SCHEDULE.get(uid, []))
            lines.append(f"• {info['name']} ({info['nick']}) — {slot_count} слотов\n  ID: <code>{uid}</code>")

        registered = get_all_registered_users()
        if registered:
            lines.append("\n<b>Зарегистрированные пользователи:</b>\n")
            for u in registered:
                status = "⏸" if u.get("paused") else "✅"
                lines.append(
                    f"• {status} {u['name']} — {u['schedule_type']}, {u['style']}\n"
                    f"  ID: <code>{u['telegram_id']}</code> | 💀 {u['meh_count']}/9"
                )

        await query.edit_message_text("\n".join(lines), parse_mode="HTML")

    elif action == "menu_close":
        await query.answer()
        await query.delete_message()
