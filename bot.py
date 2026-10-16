"""Точка входа бота."""
import asyncio
import logging
import traceback

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from app.config import settings
from app.db import init_db
from app.handlers import setup_routers
from app.middlewares import ClearStateOnSystemButton
from app.scheduler import bootstrap, scheduler

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


async def on_error(event: ErrorEvent):
    """Глобальный обработчик ошибок — логирует всё и отвечает пользователю."""
    log.error("Update error: %s", event.exception)
    log.error(traceback.format_exc())
    try:
        update = event.update
        if update.message:
            await update.message.answer(
                "Что-то пошло не так 🤔\n\n"
                "Попробуйте ещё раз или напишите /start."
            )
        elif update.callback_query:
            await update.callback_query.answer(
                "Ошибка. Попробуйте ещё раз", show_alert=True
            )
    except Exception as e:
        log.warning("Failed to notify user about error: %s", e)


async def main():
    await init_db()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(ClearStateOnSystemButton())
    dp.callback_query.middleware(ClearStateOnSystemButton())

    dp.errors.register(on_error)

    dp.include_router(setup_routers())

    scheduler.start()
    await bootstrap(bot)

    log.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())