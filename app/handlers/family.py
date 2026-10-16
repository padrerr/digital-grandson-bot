import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from app.config import settings
from app.db import (
    get_user_by_tg, get_user_family, get_user,
    list_family_members, remove_family_member,
    list_family_elderly, add_elderly,
    count_family_members, count_family_elderly,
    set_member_role, get_member_role,
    can_edit_family_data,
)
from app.keyboards import (
    kb_family_root, kb_relatives_panel, kb_elderly_panel,
    kb_family_menu,
)
from app.services.audit import log_action

log = logging.getLogger(__name__)
router = Router()


class AddElderly(StatesGroup):
    name = State()


@router.message(F.text.contains("Моя семья"))
async def family_view(msg: Message):
    user = await get_user_by_tg(msg.from_user.id)
    if not user:
        await msg.answer(
            "Я вас не вижу в базе. Отправьте /start, чтобы начать."
        )
        return
    uf = await get_user_family(user.id)
    if not uf:
        await msg.answer(
            "Похоже, вы ещё не в семье.\n\n"
            "Если вас приглашали — попросите владельца прислать ссылку "
            "заново, либо отправьте /start для создания своей семьи."
        )
        return
    f, _ = uf
    await msg.answer(
        f"<b>{f.name}</b>\nВыберите раздел:",
        reply_markup=kb_family_root(),
    )


@router.callback_query(F.data == "fam:root")
async def fam_root(cb: CallbackQuery):
    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return
    uf = await get_user_family(user.id)
    if not uf:
        await cb.answer("Семья не найдена", show_alert=True)
        return
    f, _ = uf
    await cb.message.edit_text(f"{f.name}\nВыберите раздел:",
                               reply_markup=kb_family_root())
    await cb.answer()


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer()


@router.callback_query(F.data == "fam:relatives")
async def fam_relatives(cb: CallbackQuery):
    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return
    uf = await get_user_family(user.id)
    if not uf:
        await cb.answer("Семья не найдена", show_alert=True)
        return
    f, _ = uf
    members = await list_family_members(f.id)
    text = (
        "👥 Семья — родственники\n\n"
        "👑 владелец   🔧 модератор   • участник\n\n"
        "Всего: " + str(len(members)) + " из " + str(settings.MAX_FAMILY_MEMBERS) + ".\n\n"
        "Владелец и модератор могут менять распорядок. "
        "Остальные — просматривать отчёты и писать близкому."
    )
    await cb.message.edit_text(
        text, reply_markup=kb_relatives_panel(members, f.owner_user_id, user.id)
    )
    await cb.answer()


@router.callback_query(F.data == "fam:elderly")
async def fam_elderly(cb: CallbackQuery):
    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return
    uf = await get_user_family(user.id)
    if not uf:
        await cb.answer("Семья не найдена", show_alert=True)
        return
    f, _ = uf
    elderly = await list_family_elderly(f.id)
    text = (
        "❤️ Близкие под нашей заботой\n\n"
        "Всего: " + str(len(elderly)) + " из " + str(settings.MAX_ELDERLY_PER_FAMILY) + ".\n"
        "✅ — подключён, ⏳ — ждёт приглашения."
    )
    await cb.message.edit_text(text, reply_markup=kb_elderly_panel(elderly))
    await cb.answer()


@router.callback_query(F.data.startswith("promote:"))
async def promote_member(cb: CallbackQuery):
    try:
        uid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    me = await get_user_by_tg(cb.from_user.id)
    if not me:
        await cb.answer()
        return
    uf = await get_user_family(me.id)
    if not uf or uf[0].owner_user_id != me.id:
        await cb.answer("Только владелец может назначать модератора.",
                        show_alert=True)
        return
    ok = await set_member_role(uf[0].id, uid, "moderator")
    if not ok:
        await cb.answer("Не удалось.", show_alert=True)
        return
    await log_action(me.id, uf[0].id, "promote_moderator", str(uid))
    await cb.answer("Назначен модератором")
    target = await get_user(uid)
    if target:
        try:
            await cb.bot.send_message(
                target.tg_id,
                "🔧 Вас назначили модератором семьи. "
                "Теперь вы можете менять распорядок близких."
            )
        except Exception:
            pass
    await fam_relatives(cb)


@router.callback_query(F.data.startswith("demote:"))
async def demote_member(cb: CallbackQuery):
    try:
        uid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    me = await get_user_by_tg(cb.from_user.id)
    if not me:
        await cb.answer()
        return
    uf = await get_user_family(me.id)
    if not uf or uf[0].owner_user_id != me.id:
        await cb.answer("Только владелец может снимать модератора.",
                        show_alert=True)
        return
    ok = await set_member_role(uf[0].id, uid, "member")
    if not ok:
        await cb.answer("Не удалось.", show_alert=True)
        return
    await log_action(me.id, uf[0].id, "demote_moderator", str(uid))
    await cb.answer("Права модератора сняты")
    target = await get_user(uid)
    if target:
        try:
            await cb.bot.send_message(
                target.tg_id,
                "Права модератора сняты. Теперь вы можете просматривать "
                "отчёты и писать близкому."
            )
        except Exception:
            pass
    await fam_relatives(cb)


@router.callback_query(F.data.startswith("del_member:"))
async def del_member(cb: CallbackQuery):
    try:
        uid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    me = await get_user_by_tg(cb.from_user.id)
    if not me:
        await cb.answer()
        return
    uf = await get_user_family(me.id)
    if not uf or uf[0].owner_user_id != me.id:
        await cb.answer("Только владелец может удалять.", show_alert=True)
        return
    f, _ = uf
    if uid == me.id:
        await cb.answer("Нельзя удалить самого себя.", show_alert=True)
        return
    ok = await remove_family_member(f.id, uid)
    if not ok:
        await cb.answer("Не удалось.", show_alert=True)
        return
    await log_action(me.id, f.id, "remove_member", str(uid))
    target = await get_user(uid)
    await cb.answer("Удалён", show_alert=True)
    if target:
        try:
            await cb.bot.send_message(target.tg_id, "Вас исключили из семьи.")
        except Exception:
            pass
    await fam_relatives(cb)


@router.callback_query(F.data == "add_elderly")
async def add_elderly_start(cb: CallbackQuery, state: FSMContext):
    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return
    uf = await get_user_family(user.id)
    if not uf:
        await cb.answer("Семья не найдена", show_alert=True)
        return
    f, _ = uf
    if not await can_edit_family_data(f.id, user.id):
        await cb.answer("У вас нет прав на изменение.", show_alert=True)
        return
    count = await count_family_elderly(f.id)
    if count >= settings.MAX_ELDERLY_PER_FAMILY:
        await cb.answer(
            "Достигнут лимит близких в семье (" + str(settings.MAX_ELDERLY_PER_FAMILY) + ").",
            show_alert=True,
        )
        return
    await state.set_state(AddElderly.name)
    await cb.message.edit_text("Как зовут близкого человека?")
    await cb.answer()


@router.message(AddElderly.name, F.text, ~F.text.startswith("/"))
async def add_elderly_finish(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if not txt:
        await msg.answer("Пожалуйста, напишите текстом.")
        return
    user = await get_user_by_tg(msg.from_user.id)
    if not user:
        await state.clear()
        return
    uf = await get_user_family(user.id)
    if not uf:
        await state.clear()
        await msg.answer("Семья не найдена. /start")
        return
    f, _ = uf
    count = await count_family_elderly(f.id)
    if count >= settings.MAX_ELDERLY_PER_FAMILY:
        await state.clear()
        await msg.answer("Достигнут лимит близких.")
        return
    e = await add_elderly(f.id, txt)
    await log_action(user.id, f.id, "add_elderly", e.name)
    await state.clear()
    bot_username = (await msg.bot.me()).username
    link = "https://t.me/" + bot_username + "?start=eld_" + e.invite_code
    text = "Добавлен(а): " + e.name + "\n\nСсылку открывает сам близкий:\n" + link
    await msg.answer(text, reply_markup=kb_family_menu())


@router.callback_query(F.data == "invite_member")
async def invite_member(cb: CallbackQuery):
    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return
    uf = await get_user_family(user.id)
    if not uf:
        await cb.answer("Семья не найдена", show_alert=True)
        return
    f, _ = uf
    if f.owner_user_id != user.id:
        await cb.answer("Только владелец может приглашать.", show_alert=True)
        return
    count = await count_family_members(f.id)
    if count >= settings.MAX_FAMILY_MEMBERS:
        await cb.answer(
            "Достигнут лимит участников семьи (" + str(settings.MAX_FAMILY_MEMBERS) + ").",
            show_alert=True,
        )
        return
    bot_username = (await cb.bot.me()).username
    link = "https://t.me/" + bot_username + "?start=fam_" + str(f.id)
    await log_action(user.id, f.id, "invite_member_link")
    await cb.message.edit_text(
        "Ссылка для приглашения родственника:\n" + link + "\n\n"
        "После присоединения он получит права участника. "
        "Назначить модератора можно из списка семьи.",
        reply_markup=kb_relatives_panel(
            await list_family_members(f.id), f.owner_user_id, user.id
        ),
    )
    await cb.answer()