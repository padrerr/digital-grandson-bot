import logging

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from app.config import settings
from app.db import (
    get_user_by_tg, create_user, get_user_family, get_elderly_by_user,
    get_elderly_by_code, get_family, add_family_member,
    link_elderly_user, create_family, count_family_members,
    count_family_elderly,
)
from app.keyboards import (
    kb_role, kb_consent, kb_family_menu, kb_elderly_menu,
)

log = logging.getLogger(__name__)
router = Router()


class Registration(StatesGroup):
    family_name = State()
    family_title = State()


@router.message(CommandStart())
async def start(msg: Message, state: FSMContext):
    parts = msg.text.split(maxsplit=1)
    payload = parts[1] if len(parts) > 1 else None
    existing = await get_user_by_tg(msg.from_user.id)

    if payload and payload.startswith("eld_"):
        return await _handle_elderly_invite(msg, state, existing, payload[4:])

    if payload and payload.startswith("fam_"):
        return await _handle_family_invite(msg, state, existing, payload[4:])

    if existing:
        return await _greet_existing(msg, existing)

    await msg.answer(
        "Здравствуйте! Это «Цифровой внук». Кто вы?",
        reply_markup=kb_role(),
    )


async def _handle_elderly_invite(msg, state, existing, code):
    if existing:
        uf = await get_user_family(existing.id)
        eld_existing = await get_elderly_by_user(existing.id)
        if eld_existing:
            await msg.answer("Вы уже подключены как близкий человек.",
                             reply_markup=kb_elderly_menu())
            return
        if uf:
            await msg.answer(
                "⚠️ Вы уже зарегистрированы как родственник.\n\n"
                "Эта ссылка — для близкого человека. Не открывайте её со "
                "своего аккаунта.\n\n"
                "Если хотите стать «близким» — удалите аккаунт "
                "(«⚙️ Аккаунт» → «🗑 Удалить аккаунт»)."
            )
            return
        e = await get_elderly_by_code(code)
        if not e:
            await msg.answer("Ссылка недействительна.")
            return
        if e.user_id:
            await msg.answer("Ссылка уже использована.")
            return
        await link_elderly_user(e.id, existing.id)
        await msg.answer(f"Готово! Вы подключены как {e.name}.",
                         reply_markup=kb_elderly_menu())
        return

    await state.update_data(elderly_code=code)
    await msg.answer(
        "Здравствуйте! Вас пригласили в семейный сервис.\n"
        "Нужно ваше согласие на обработку данных (152-ФЗ). "
        "Политика: /privacy",
        reply_markup=kb_consent(),
    )


async def _handle_family_invite(msg, state, existing, code):
    if existing:
        uf = await get_user_family(existing.id)
        if uf:
            await msg.answer("Вы уже в семье.")
            return
        eld = await get_elderly_by_user(existing.id)
        if eld:
            await msg.answer(
                "⚠️ Вы зарегистрированы как близкий человек и не можете "
                "присоединиться к семье как родственник. "
                "Удалите аккаунт («⚙️ Аккаунт»)."
            )
            return
        if not code.isdigit():
            await msg.answer("Ссылка недействительна.")
            return
        f = await get_family(int(code))
        if not f:
            await msg.answer("Ссылка недействительна.")
            return
        if await count_family_members(f.id) >= settings.MAX_FAMILY_MEMBERS:
            await msg.answer(
                "В семье уже максимальное количество участников ("
                + str(settings.MAX_FAMILY_MEMBERS) + ")."
            )
            return
        await add_family_member(f.id, existing.id)
        await msg.answer(f"Вы присоединились к семье «{f.name}».",
                         reply_markup=kb_family_menu())
        return

    await state.update_data(family_code=code)
    await msg.answer(
        "Здравствуйте! Вас пригласили в семейную группу.\n"
        "Нужно ваше согласие на обработку данных (152-ФЗ). "
        "Политика: /privacy",
        reply_markup=kb_consent(),
    )


async def _greet_existing(msg, existing):
    uf = await get_user_family(existing.id)
    eld = await get_elderly_by_user(existing.id)
    if eld:
        await msg.answer("С возвращением!", reply_markup=kb_elderly_menu())
    elif uf:
        await msg.answer("С возвращением!", reply_markup=kb_family_menu())
    else:
        await msg.answer("Похоже, вы ещё не в семье. Начните заново.",
                         reply_markup=kb_role())


@router.callback_query(F.data == "consent:no")
async def consent_no(cb: CallbackQuery):
    await cb.message.edit_text("Без согласия работа невозможна. /start для повтора.")
    await cb.answer()


@router.callback_query(F.data == "consent:yes")
async def consent_yes(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tg = cb.from_user.id
    user = await get_user_by_tg(tg) or await create_user(tg, "")

    if data.get("elderly_code"):
        return await _finish_elderly_consent(cb, state, user)

    if data.get("family_code"):
        return await _finish_family_consent(cb, state, user)

    await state.set_state(Registration.family_name)
    await cb.message.edit_text("Спасибо! Напишите, как вас зовут:")
    await cb.answer()


async def _finish_elderly_consent(cb, state, user):
    data = await state.get_data()
    e = await get_elderly_by_code(data.get("elderly_code", ""))
    if not e or e.user_id:
        await cb.message.edit_text("Ссылка недействительна.")
        await cb.answer()
        return
    await link_elderly_user(e.id, user.id)
    await state.clear()
    await cb.message.edit_text(f"Готово! Вы — {e.name}.")
    await cb.bot.send_message(cb.from_user.id, "Меню:",
                              reply_markup=kb_elderly_menu())
    await cb.answer()


async def _finish_family_consent(cb, state, user):
    data = await state.get_data()
    code = data.get("family_code", "")
    if not code.isdigit():
        await cb.message.edit_text("Ссылка недействительна.")
        await cb.answer()
        return
    f = await get_family(int(code))
    uf = await get_user_family(user.id)
    if not f or uf:
        await cb.message.edit_text("Ссылка недействительна.")
        await cb.answer()
        return
    if await count_family_members(f.id) >= settings.MAX_FAMILY_MEMBERS:
        await cb.message.edit_text(
            "В семье уже максимальное количество участников ("
            + str(settings.MAX_FAMILY_MEMBERS) + ")."
        )
        await cb.answer()
        return
    await add_family_member(f.id, user.id)
    await state.clear()
    await cb.message.edit_text(f"Вы в семье «{f.name}».")
    await cb.bot.send_message(cb.from_user.id, "Меню:",
                              reply_markup=kb_family_menu())
    await cb.answer()


@router.callback_query(F.data.startswith("role:"))
async def choose_role(cb: CallbackQuery):
    role = cb.data.split(":")[1]
    if role == "elderly":
        await cb.message.edit_text(
            "Для регистрации как близкий человек нужно приглашение от семьи. "
            "Пусть родственник отправит вам ссылку."
        )
        await cb.answer()
        return
    await cb.message.edit_text(
        "Для работы нужно согласие на обработку ПДн (152-ФЗ). "
        "Политика: /privacy",
        reply_markup=kb_consent(),
    )
    await cb.answer()


@router.message(Registration.family_name, F.text, ~F.text.startswith("/"))
async def reg_name(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if not txt:
        await msg.answer("Пожалуйста, напишите текстом.")
        return
    from app.db import Session, User
    user = await get_user_by_tg(msg.from_user.id)
    if not user:
        user = await create_user(msg.from_user.id, txt)
    else:
        async with Session() as s:
            u = await s.get(User, user.id)
            u.name = txt
            await s.commit()
    await state.update_data(owner_id=user.id)
    await state.set_state(Registration.family_title)
    await msg.answer("Как назвать семью? Например: «Семья Ивановых»")


@router.message(Registration.family_title, F.text, ~F.text.startswith("/"))
async def reg_family(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if not txt:
        await msg.answer("Пожалуйста, напишите текстом.")
        return
    user = await get_user_by_tg(msg.from_user.id)
    if not user:
        await msg.answer("Сессия потеряна. /start")
        return
    f = await create_family(user, txt)
    await state.clear()
    await msg.answer(
        f"Семья «{f.name}» создана. Нажмите «👨‍👩‍👧 Моя семья».",
        reply_markup=kb_family_menu(),
    )