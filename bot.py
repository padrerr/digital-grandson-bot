"""Точка входа бота."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.db import init_db
from app.handlers import setup_routers
from app.scheduler import bootstrap, scheduler

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


async def main():
    await init_db()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher(storage=MemoryStorage())
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