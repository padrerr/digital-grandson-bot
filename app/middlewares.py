import logging
import traceback

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.constants import SYSTEM_BUTTONS

log = logging.getLogger(__name__)

# Inline-кнопки, при нажатии на которые нужно сбросить FSM state
CALLBACK_RESET_PREFIXES = (
    "fam:",
    "eld:",
    "rt_menu:",
    "rt_back:",
    "pick_cancel",
    "prob:cancel",
    "adm_",
    "tpl:",
    "tpl_my:",
    "notes:",
)


class ClearStateOnSystemButton(BaseMiddleware):
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
                log.info("Callback: %s", event.data)
                state: FSMContext = data.get("state")
                if state:
                    current = await state.get_state()
                    if current and event.data:
                        # Сбрасываем, если нажата навигационная кнопка
                        for prefix in CALLBACK_RESET_PREFIXES:
                            if event.data.startswith(prefix):
                                log.info(
                                    "Clear state %s on callback %s",
                                    current, event.data,
                                )
                                await state.clear()
                                break

            return await handler(event, data)
        except Exception as e:
            log.error("Middleware error: %s", e)
            log.error(traceback.format_exc())
            raise