"""
Админ-панель.

Содержит:
  • /admin — открыть панель
  • сводку, списки семей и близких
  • список заявок и ответ на них
"""
import logging
from datetime import date

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from app.services.backup import list_backups
from app.services.monitor import last_heartbeat

from app.config import settings
from app.db import (
    Session, User,
    get_user_by_tg, get_user, list_admins,
    list_all_families, list_family_elderly, list_family_members,
    list_all_elderly,
    list_all_help_requests, get_help_request, reply_help_request,
    admin_stats,
)
from app.keyboards import kb_admin, kb_admin_help_list, kb_admin_help_detail

log = logging.getLogger(__name__)
router = Router()


class AdminReply(StatesGroup):
    enter_text = State()


def is_admin(tg_id: int, user) -> bool:
    if tg_id in settings.admin_ids:
        return True
    return bool(user and user.is_admin)


# ============================================================
# /admin
# ============================================================

        await msg.answer(
            "Нет доступа.\n"
            "Ваш ID: " + str(tg) + "\n"
            "ADMIN_IDS: " + str(settings.admin_ids)
        )
        return

@router.callback_query(F.data == "adm_back")
async def admin_back(cb: CallbackQuery):
    tg = cb.from_user.id
    user = await get_user_by_tg(tg)
    if not is_admin(tg, user):
        await cb.answer("Нет доступа", show_alert=True)
        return
    await cb.message.edit_text("Админ-панель:", reply_markup=kb_admin())
    await cb.answer()


# ============================================================
# СВОДКА
# ============================================================

@router.callback_query(F.data == "adm_stats")
async def admin_stats_view(cb: CallbackQuery):
    tg = cb.from_user.id
    user = await get_user_by_tg(tg)
    if not is_admin(tg, user):
        await cb.answer("Нет доступа", show_alert=True)
        return

    s = await admin_stats()
    await cb.message.edit_text(
        f"📊 <b>Сводка</b>\n\n"
        f"👨‍👩‍👧 Семей: <b>{s['families']}</b>\n"
        f"👥 Пользователей: <b>{s['users']}</b>\n"
        f"❤️ Близких: <b>{s['elderly']}</b> (подключено: {s['linked_elderly']})\n"
        f"☀️ Проснулись сегодня: <b>{s['awake_today']}</b>\n"
        f"📋 Событий сегодня: {s['events_today']}\n"
        f"🚨 Тревог сегодня: <b>{s['alarms_today']}</b>\n\n"
        f"📨 Заявок:\n"
        f"  • сегодня: <b>{s['help_today']}</b>\n"
        f"  • новых: <b>{s['help_new']}</b>\n"
        f"  • всего: {s['help_total']}",
        reply_markup=kb_admin(),
    )
    await cb.answer()


# ============================================================
# СПИСКИ
# ============================================================

@router.callback_query(F.data == "adm_families")
async def admin_families(cb: CallbackQuery):
    tg = cb.from_user.id
    user = await get_user_by_tg(tg)
    if not is_admin(tg, user):
        await cb.answer("Нет доступа", show_alert=True)
        return

    fams = await list_all_families()
    if not fams:
        await cb.message.edit_text("Семей пока нет.", reply_markup=kb_admin())
        await cb.answer()
        return

    lines = ["👨‍👩‍👧 <b>Семьи</b>"]
    for f in fams:
        eld = await list_family_elderly(f.id)
        members = await list_family_members(f.id)
        lines.append(
            f"\n<b>#{f.id} «{f.name}»</b>\n"
            f"Родственников: {len(members)}, близких: {len(eld)}"
        )
    await cb.message.edit_text("\n".join(lines), reply_markup=kb_admin())
    await cb.answer()


@router.callback_query(F.data == "adm_elderly")
async def admin_elderly(cb: CallbackQuery):
    tg = cb.from_user.id
    user = await get_user_by_tg(tg)
    if not is_admin(tg, user):
        await cb.answer("Нет доступа", show_alert=True)
        return

    elds = await list_all_elderly()
    if not elds:
        await cb.message.edit_text("Близких пока нет.", reply_markup=kb_admin())
        await cb.answer()
        return

    lines = ["❤️ <b>Близкие</b>"]
    today = date.today().isoformat()
    for e in elds:
        woke = "☀️" if e.wake_date == today else "—"
        link = "✅" if e.user_id else "⏳"
        act = "🟢" if e.active else "⏸"
        quiet = "🌙" if e.quiet_enabled else ""
        lines.append(
            f"\n<b>#{e.id} {e.name}</b> {act}{quiet}\n"
            f"Семья: #{e.family_id}, подключён: {link}, сегодня: {woke}"
        )
    await cb.message.edit_text("\n".join(lines), reply_markup=kb_admin())
    await cb.answer()


# ============================================================
# ЗАЯВКИ О ПОМОЩИ
# ============================================================

@router.callback_query(F.data == "adm_help")
async def admin_help(cb: CallbackQuery):
    tg = cb.from_user.id
    user = await get_user_by_tg(tg)
    if not is_admin(tg, user):
        await cb.answer("Нет доступа", show_alert=True)
        return

    reqs = await list_all_help_requests()
    if not reqs:
        await cb.message.edit_text("Заявок пока нет.", reply_markup=kb_admin())
        await cb.answer()
        return

    new_cnt = sum(1 for r in reqs if r.status == "new")
    text = f"📨 <b>Заявки ({len(reqs)})</b>\n🆕 новые — {new_cnt}"
    await cb.message.edit_text(text, reply_markup=kb_admin_help_list(reqs[:50]))
    await cb.answer()


@router.callback_query(F.data.startswith("adm_hr:"))
async def admin_help_view(cb: CallbackQuery):
    tg = cb.from_user.id
    user = await get_user_by_tg(tg)
    if not is_admin(tg, user):
        await cb.answer("Нет доступа", show_alert=True)
        return

    try:
        rid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return

    hr = await get_help_request(rid)
    if not hr:
        await cb.answer("Заявка не найдена", show_alert=True)
        return

    author = await get_user(hr.user_id)
    d = hr.created_at.strftime("%d.%m.%Y %H:%M")
    text = (
        f"📨 <b>Заявка #{hr.id}</b>\n"
        f"От: {author.name if author else '—'}\n"
        f"Дата: {d}\n\n<b>Текст:</b>\n{hr.request_text}"
    )
    if hr.reply_text:
        text += f"\n\n<b>Ваш ответ:</b>\n{hr.reply_text}"

    await cb.message.edit_text(
        text,
        reply_markup=kb_admin_help_detail(rid, can_reply=(hr.status == "new")),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("adm_hr_reply:"))
async def admin_help_reply_start(cb: CallbackQuery, state: FSMContext):
    tg = cb.from_user.id
    user = await get_user_by_tg(tg)
    if not is_admin(tg, user):
        await cb.answer("Нет доступа", show_alert=True)
        return

    try:
        rid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return

    hr = await get_help_request(rid)
    if not hr:
        await cb.answer("Заявка не найдена", show_alert=True)
        return

    await state.update_data(reply_rid=rid)
    await state.set_state(AdminReply.enter_text)
    await cb.message.edit_text(f"Введите текст ответа для заявки #{rid}:")
    await cb.answer()


@router.message(AdminReply.enter_text, F.text, ~F.text.startswith("/"))
async def admin_help_reply_send(msg: Message, state: FSMContext):
    tg = msg.from_user.id
    user = await get_user_by_tg(tg)
    if not is_admin(tg, user):
        await state.clear()
        return

    txt = (msg.text or "").strip()
    if not txt:
        await msg.answer("Пожалуйста, напишите текстом.")
        return

    data = await state.get_data()
    rid = data.get("reply_rid")
    hr = await get_help_request(rid)
    if not hr:
        await state.clear()
        await msg.answer("Заявка не найдена.", reply_markup=kb_admin())
        return

    await reply_help_request(rid, txt)
    await state.clear()
    await msg.answer(f"✅ Ответ отправлен по заявке #{rid}.",
                     reply_markup=kb_admin())

    author = await get_user(hr.user_id)
    if author:
        try:
            await msg.bot.send_message(
                author.tg_id,
                f"📨 Ответ по вашей заявке #{rid}:\n\n{txt}\n\n"
                f"Посмотреть все: «📨 Мои заявки»"
            )
        except Exception as ex:
            log.warning("author notify failed: %s", ex)

@router.callback_query(F.data == "adm_backups")
async def admin_backups(cb: CallbackQuery):
    tg = cb.from_user.id
    user = await get_user_by_tg(tg)
    if not is_admin(tg, user):
        await cb.answer("Нет доступа", show_alert=True)
        return
    items = list_backups()
    hb = last_heartbeat()
    lines = ["💾 Бэкапы базы", ""]
    if hb:
        delta = datetime.utcnow() - hb
        mins = int(delta.total_seconds() / 60)
        lines.append("Heartbeat: " + str(mins) + " мин назад")
    else:
        lines.append("Heartbeat: нет данных")
    lines.append("")
    if not items:
        lines.append("Пока нет бэкапов.")
    else:
        for it in items[:15]:
            lines.append(
                it["date"].strftime("%d.%m %H:%M") +
                "  " + str(it["size_kb"]) + " КБ"
            )
    from app.keyboards import kb_admin
    await cb.message.edit_text("\n".join(lines), reply_markup=kb_admin())
    await cb.answer()            