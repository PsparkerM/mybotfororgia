import logging
from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeDefault, MenuButtonCommands
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters,
)
from config import BOT_TOKEN, ADMIN_ID
from handlers import (
    # Onboarding conversation
    start_handler, gender_callback, name_callback, style_callback, schedule_callback,
    GENDER, NAME, STYLE, SCHEDULE_TYPE,
    # Admin commands
    status_handler, sendnow_handler, broadcast_handler, dm_handler,
    menu_handler, restart_handler, testdb_handler,
    addchat_handler, removechat_handler, listchats_handler, testall_handler,
    # Callbacks
    reaction_callback, meh_callback, menu_callback,
    meh_step1_callback, meh_step2_callback, meh_step3_callback,
    # Message forwarding
    user_message_handler,
    # Group chat
    bot_added_to_group_handler, group_message_handler,
)
from scheduler import scheduler, setup_jobs

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    scheduler.start()
    setup_jobs(application.bot)

    await application.bot.set_my_commands(
        [BotCommand("start", "Запустить бота")],
        scope=BotCommandScopeDefault(),
    )
    await application.bot.set_my_commands(
        [
            BotCommand("start",       "Запустить бота"),
            BotCommand("menu",        "Открыть меню"),
            BotCommand("status",      "Статус всех задач"),
            BotCommand("sendnow",     "Отправить слот сейчас"),
            BotCommand("dm",          "Написать одному пользователю"),
            BotCommand("broadcast",   "Рассылка всем"),
            BotCommand("restart",     "Возобновить мотивацию пользователя"),
            BotCommand("addchat",     "Добавить чат в мониторинг"),
            BotCommand("removechat",  "Убрать чат из мониторинга"),
            BotCommand("listchats",   "Список мониторинговых чатов"),
        ],
        scope=BotCommandScopeChat(chat_id=ADMIN_ID),
    )
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())

    logger.info("Scheduler started — all jobs loaded")


def main() -> None:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Onboarding ConversationHandler (replaces simple /start handler)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_handler)],
        states={
            GENDER:        [CallbackQueryHandler(gender_callback,   pattern=r"^reg_gender_")],
            NAME:          [MessageHandler(filters.TEXT & ~filters.COMMAND, name_callback)],
            STYLE:         [CallbackQueryHandler(style_callback,    pattern=r"^reg_style_")],
            SCHEDULE_TYPE: [CallbackQueryHandler(schedule_callback, pattern=r"^reg_sched_")],
        },
        fallbacks=[CommandHandler("start", start_handler)],
        per_message=False,
    )
    app.add_handler(conv_handler)

    # Admin commands
    app.add_handler(CommandHandler("status",     status_handler))
    app.add_handler(CommandHandler("sendnow",    sendnow_handler))
    app.add_handler(CommandHandler("dm",         dm_handler))
    app.add_handler(CommandHandler("broadcast",  broadcast_handler))
    app.add_handler(CommandHandler("menu",       menu_handler))
    app.add_handler(CommandHandler("restart",    restart_handler))
    app.add_handler(CommandHandler("testdb",     testdb_handler))
    app.add_handler(CommandHandler("testall",    testall_handler))
    app.add_handler(CommandHandler("addchat",    addchat_handler))
    app.add_handler(CommandHandler("removechat", removechat_handler))
    app.add_handler(CommandHandler("listchats",  listchats_handler))

    # Group chat: detect when bot is added, then handle messages
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot_added_to_group_handler))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, group_message_handler))

    # Private message forwarding (must come AFTER ConversationHandler and group handlers)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, user_message_handler))

    # Reaction callbacks
    app.add_handler(CallbackQueryHandler(reaction_callback,   pattern=r"^ack_"))
    app.add_handler(CallbackQueryHandler(meh_callback,        pattern=r"^meh_\d"))
    app.add_handler(CallbackQueryHandler(meh_step1_callback,  pattern=r"^mehc1_"))
    app.add_handler(CallbackQueryHandler(meh_step2_callback,  pattern=r"^mehc2_"))
    app.add_handler(CallbackQueryHandler(meh_step3_callback,  pattern=r"^mehc3_"))
    app.add_handler(CallbackQueryHandler(menu_callback,       pattern=r"^menu_"))

    logger.info("Bot is starting (polling mode)...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
