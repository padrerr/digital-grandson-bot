import logging
import traceback

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.constants import SYSTEM_BUTTONS

log = logging.getLogger(__name__)


class ClearStateOnSystemButton(BaseMiddleware):
    """
    Если пользователь нажал системную кнопку меню — сбрасываем FSM state.
    Также логируем любое сообщение/нажатие для отладки.
    """

    async def __call__(self, handler, event, data):
        try:
            if isinstance(event, Message):
                txt = (event.text or "").strip()
                if txt and txt in SYSTEM_BUTTONS:
                    state: FSMContext = data.get("state")
                    if state:
                        current = await state.get_state()
                        if current:
                            log.info(
                                "Clear state %s (system button: %r)",
                                current, txt,
                            )
                            await state.clear()

            elif isinstance(event, CallbackQuery):
                # логируем все нажатия inline-кнопок
                log.info("Callback: %s", event.data)
                # если state есть — сбрасываем, чтобы не блокировал
                state: FSMContext = data.get("state")
                if state:
                    current = await state.get_state()
                    # сбрасываем только для "корневых" меню-навигаций
                    if current and event.data and (
                        event.data in ("fam:root", "fam:relatives", "fam:elderly")
                        or event.data.startswith("adm_")
                    ):
                        log.info("Clear state %s on callback %s", current, event.data)
                        await state.clear()

            return await handler(event, data)
        except Exception as e:
            log.error("Middleware error: %s", e)
            log.error(traceback.format_exc())
            raise