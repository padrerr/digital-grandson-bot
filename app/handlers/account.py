"""
Личный кабинет и удаление аккаунта.

Содержит:
  • «⚙️ Аккаунт» — информация о пользователе
  • подтверждение удаления
  • само удаление
"""
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from app.db import (
    get_user_by_tg, get_user_family, get_elderly_by_user,
    list_family_members, delete_user_everything,
)
from app.keyboards import kb_account_menu, kb_account_delete_confirm

log = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "⚙️ Аккаунт")
async def account_view(msg: Message):
    user = await get_user_by_tg(msg.from_user.id)
    if not user:
        return

    uf = await get_user_family(user.id)
    eld = await get_elderly_by_user(user.id)

    if eld:
        role = "Близкий человек"
    elif uf:
        role = "Владелец семьи" if uf[1] == "owner" else "Родственник"
    else:
        role = "—"

    await msg.answer(
        f"⚙️ <b>Аккаунт</b>\n\n"
        f"Имя: {user.name or '—'}\n"
        f"Telegram ID: <code>{user.tg_id}</code>\n"
        f"Роль: {role}\n\n"
        f"Хотите сменить роль? Удалите аккаунт и зарегистрируйтесь заново.",
        reply_markup=kb_account_menu(),
    )


@router.callback_query(F.data == "acc:delete_confirm")
async def delete_confirm(cb: CallbackQuery):
    await cb.message.edit_text(
        "🗑 <b>Удаление аккаунта</b>\n\n"
        "Будут удалены все ваши данные и роли. Продолжить?",
        reply_markup=kb_account_delete_confirm(),
    )
    await cb.answer()


@router.callback_query(F.data == "acc:cancel")
async def delete_cancel(cb: CallbackQuery):
    await cb.message.edit_text("Отменено.")
    await cb.answer()


@router.callback_query(F.data == "acc:delete_yes")
async def delete_yes(cb: CallbackQuery):
    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return

    uf = await get_user_family(user.id)
    fam_members = []
    if uf:
        fam_members = await list_family_members(uf[0].id)

    await delete_user_everything(user.id)

    await cb.message.edit_text("✅ Аккаунт удалён. /start — начать заново.")
    await cb.answer("Удалено")

    # уведомляем семью
    for m, _ in fam_members:
        if m.id == user.id:
            continue
        try:
            await cb.bot.send_message(
                m.tg_id, f"ℹ️ {user.name or 'Участник'} покинул(а) семью."
            )
        except Exception as ex:
            log.warning("notify failed: %s", ex)