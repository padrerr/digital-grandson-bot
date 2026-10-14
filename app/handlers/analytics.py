import logging
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.db import (
    get_user_by_tg, get_user_family, list_family_elderly,
    get_elderly, weekly_progress, family_activity_log,
    get_elderly_names,
)
from app.keyboards import kb_analytics_elderly_pick

log = logging.getLogger(__name__)
router = Router()


WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _bar(stats):
    parts = []
    for _ in range(stats.get("done", 0)):
        parts.append("✅")
    for _ in range(stats.get("skipped", 0)):
        parts.append("⏭")
    for _ in range(stats.get("alarm", 0)):
        parts.append("⚠️")
    if not parts:
        parts.append("—")
    return "".join(parts)


def _back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ К отчётам", callback_data="rep_root")],
    ])


@router.callback_query(F.data == "an:week")
async def analytics_week_start(cb: CallbackQuery):
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
    if not elderly:
        await cb.answer("В семье нет близких.", show_alert=True)
        return
    if len(elderly) == 1:
        await _show_week(cb, elderly[0].id)
        return
    await cb.message.edit_text(
        "Прогресс за неделю — выберите близкого:",
        reply_markup=kb_analytics_elderly_pick(elderly, prefix="an:week_e"),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("an:week_e:"))
async def analytics_week_pick(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[2])
    except (ValueError, IndexError):
        await cb.answer()
        return
    await _show_week(cb, eid)
    await cb.answer()


async def _show_week(cb: CallbackQuery, elderly_id: int):
    e = await get_elderly(elderly_id)
    if not e:
        await cb.answer("Не найден", show_alert=True)
        return
    days = await weekly_progress(elderly_id, days=7)
    total_done = 0
    total_all = 0
    lines = ["📈 Прогресс за 7 дней — " + e.name, ""]
    for d in days:
        date = d["date"]
        wd = WEEKDAYS[date.weekday()]
        ds = date.strftime("%d.%m")
        bar = _bar(d)
        done = d.get("done", 0)
        total = d.get("total", 0)
        total_done = total_done + done
        total_all = total_all + total
        lines.append(wd + " " + ds + "  " + bar + "   " +
                     str(done) + "/" + str(total))
    lines.append("")
    if total_all > 0:
        percent = int(total_done * 100 / total_all)
        lines.append("Всего: " + str(total_done) + " из " +
                     str(total_all) + " (" + str(percent) + "%)")
    else:
        lines.append("Пока нет данных за эту неделю.")
    text = "\n".join(lines)
    await cb.message.edit_text(text, reply_markup=_back_kb())


@router.callback_query(F.data == "an:log")
async def analytics_log(cb: CallbackQuery):
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
    if not elderly:
        await cb.answer("В семье нет близких.", show_alert=True)
        return
    ids = [e.id for e in elderly]
    names = await get_elderly_names(ids)
    items = await family_activity_log(f.id, ids, hours=24, limit=50)

    if not items:
        await cb.message.edit_text(
            "📋 Семейный лог за сутки\n\n"
            "Пока нет событий. Как только близкие начнут отмечать "
            "задачи и писать сообщения — здесь всё появится.",
            reply_markup=_back_kb(),
        )
        await cb.answer()
        return

    lines = ["📋 Семейный лог за сутки", ""]
    multi = len(ids) > 1
    for created, t, text, eid in items[:30]:
        name = names.get(eid, "")
        prefix = ""
        if multi and name:
            prefix = name + ": "
        lines.append(t + "  " + prefix + text)
    text = "\n".join(lines)
    try:
        await cb.message.edit_text(text, reply_markup=_back_kb())
    except Exception:
        await cb.message.answer(text, reply_markup=_back_kb())
    await cb.answer()