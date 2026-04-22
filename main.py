import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from config import BOT_TOKEN
from handlers import (
    start_handler, status_handler, sendnow_handler,
    broadcast_handler, dm_handler, menu_handler,
    reaction_callback, menu_callback,
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
    logger.info("Scheduler started — all jobs loaded")


def main() -> None:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("status", status_handler))
    app.add_handler(CommandHandler("sendnow", sendnow_handler))
    app.add_handler(CommandHandler("dm", dm_handler))
    app.add_handler(CommandHandler("broadcast", broadcast_handler))
    app.add_handler(CommandHandler("menu", menu_handler))

    app.add_handler(CallbackQueryHandler(reaction_callback, pattern=r"^ack_"))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu_"))

    logger.info("Bot is starting (polling mode)...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
