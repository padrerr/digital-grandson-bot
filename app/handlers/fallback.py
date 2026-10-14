from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.db import get_user_by_tg, get_elderly_by_user, get_user_family

router = Router()


FALLBACK_FAMILY = (
    "Я вас не понял 🤔\n\n"
    "Пожалуйста, выберите нужное действие на клавиатуре внизу экрана:\n"
    "• 👨‍👩‍👧 Моя семья — родственники и близкие\n"
    "• 📊 Отчёты — статистика за неделю\n"
    "• ✉️ Отправить сообщение близкому\n"
    "• 🛠 Написать в техподдержку\n"
    "• ❓ Как пользоваться ботом?\n\n"
    "Если что-то не работает — напишите в техподдержку."
)

FALLBACK_ELDERLY = (
    "Я вас не понял 🤔\n\n"
    "Пожалуйста, выберите нужное действие на клавиатуре внизу:\n"
    "• ☀️ Я проснулся — начать день\n"
    "• 😊 Как я себя чувствую — сообщить о самочувствии\n"
    "• 📋 Мои задачи — что делать сегодня\n"
    "• 📷 Отправить фото — показать близким\n"
    "• ✉️ Отправить сообщение родственнику\n\n"
    "Или просто напишите словами, как вы себя чувствуете."
)

FALLBACK_UNKNOWN = (
    "Здравствуйте! Чтобы начать работу, отправьте /start.\n\n"
    "Если вы уже зарегистрированы — откройте меню кнопок внизу экрана."
)


async def _is_elderly(tg_id):
    user = await get_user_by_tg(tg_id)
    if not user:
        return None
    e = await get_elderly_by_user(user.id)
    if e:
        return "elderly"
    uf = await get_user_family(user.id)
    if uf:
        return "family"
    return None


@router.message(F.text)
async def fallback_text(msg: Message, state: FSMContext):
    if await state.get_state():
        await msg.answer("Ответьте текстом или используйте кнопку.")
        return
    role = await _is_elderly(msg.from_user.id)
    if role == "elderly":
        await msg.answer(FALLBACK_ELDERLY)
    elif role == "family":
        await msg.answer(FALLBACK_FAMILY)
    else:
        await msg.answer(FALLBACK_UNKNOWN)


@router.message()
async def fallback_any(msg: Message):
    await msg.answer(
        "Я умею работать с текстом, голосовыми, фото и видеокружками. "
        "Выберите действие на клавиатуре внизу или отправьте /start."
    )