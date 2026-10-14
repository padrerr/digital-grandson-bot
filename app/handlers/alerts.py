import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.db import (
    get_user_by_tg, get_elderly, list_family_members,
    create_alert_ack, mute_user, unmute_user, get_mute_until,
)

log = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data.startswith("ack:"))
async def ack_alert(cb: CallbackQuery):
    parts = cb.data.split(":")
    if len(parts) < 3:
        await cb.answer()
        return
    try:
        eid = int(parts[1])
    except ValueError:
        await cb.answer()
        return
    kind = parts[2]

    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return
    e = await get_elderly(eid)
    if not e:
        await cb.answer("Уже неактуально", show_alert=True)
        return

    summary = e.name + " (" + kind + ")"
    await create_alert_ack(eid, user.id, kind, summary)

    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.message.answer(
        "✅ Вы взяли на контроль: " + e.name +
        ".\nРодственники получили уведомление."
    )

    for u, _ in await list_family_members(e.family_id):
        if u.id == user.id:
            continue
        try:
            await cb.bot.send_message(
                u.tg_id,
                "✅ " + (user.name or "Родственник") +
                " взял(а) на контроль: " + e.name +
                " (" + kind + ")"
            )
        except Exception:
            pass
    await cb.answer("Принято")


@router.callback_query(F.data.startswith("mute:"))
async def mute_cb(cb: CallbackQuery):
    parts = cb.data.split(":")
    if len(parts) != 2:
        await cb.answer()
        return
    try:
        minutes = int(parts[1])
    except ValueError:
        await cb.answer()
        return
    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return
    until = await mute_user(user.id, minutes)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.message.answer(
        "🔕 Уведомления отключены до "
        + until.strftime("%d.%m %H:%M") + ".\n\n"
        "Критические тревоги всё равно придут."
    )
    await cb.answer("Тишина включена")


@router.callback_query(F.data == "mute_off")
async def mute_off(cb: CallbackQuery):
    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return
    await unmute_user(user.id)
    try:
        await cb.message.edit_text("🔔 Уведомления включены.")
    except Exception:
        await cb.message.answer("🔔 Уведомления включены.")
    await cb.answer("Включено")


@router.callback_query(F.data == "mute_panel")
async def mute_panel(cb: CallbackQuery):
    from app.keyboards import kb_mute_panel
    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return
    until = await get_mute_until(user.id)
    if until:
        text = "🔕 Пауза до " + until.strftime("%d.%m %H:%M") + "."
    else:
        text = (
            "🔕 Пауза в уведомлениях\n\n"
            "Выберите, на сколько отключить уведомления. "
            "Критические тревоги будут приходить всегда."
        )
    await cb.message.edit_text(text, reply_markup=kb_mute_panel(until))
    await cb.answer()