import logging

from aiogram import BaseMiddleware
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.constants import SYSTEM_BUTTONS

log = logging.getLogger(__name__)


class ClearStateOnSystemButton(BaseMiddleware):
    """
    Если пользователь нажал системную кнопку меню — сбрасываем FSM state.
    Это позволяет state-обработчикам не перехватывать кнопки.
    """

    async def __call__(self, handler, event, data):
        if isinstance(event, Message):
            txt = (event.text or "").strip()
            if txt and txt in SYSTEM_BUTTONS:
                state: FSMContext = data.get("state")
                if state:
                    current = await state.get_state()
                    if current:
                        log.info(
                            "Clear state %s because user pressed system button: %r",
                            current, txt,
                        )
                        await state.clear()
        return await handler(event, data)