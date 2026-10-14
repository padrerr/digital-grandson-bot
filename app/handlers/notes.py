import logging
import re
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from app.db import (
    get_user_by_tg, get_elderly, get_routines,
    add_note, get_note, list_notes_for_elderly, mark_note_done,
    delete_note, list_family_members,
    can_edit_family_data, get_user,
)
from app.keyboards import kb_notes_menu, kb_note_view, kb_note_feedback
from app.scheduler import schedule_note, reschedule_all_notes

log = logging.getLogger(__name__)
router = Router()


class NoteAdd(StatesGroup):
    text = State()
    time = State()


def _parse_time(txt: str):
    """Принимает '14:30' или '14:30 15.11' или '15.11 14:30'. Возвращает datetime или None."""
    txt = txt.strip().replace(",", " ")
    now = datetime.now()

    # Только время — сегодня или завтра
    m = re.match(r"^(\d{1,2}):(\d{2})$", txt)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if not (0 <= h < 24 and 0 <= mi < 60):
            return None
        target = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        if target <= now:
            target = target + timedelta(days=1)
        return target

    # Дата + время: 15.11 14:30 или 14:30 15.11
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{2})$", txt)
    if m:
        d, mo, h, mi = (int(m.group(i)) for i in (1, 2, 3, 4))
    else:
        m = re.match(r"^(\d{1,2}):(\d{2})\s+(\d{1,2})\.(\d{1,2})$", txt)
        if not m:
            return None
        h, mi, d, mo = (int(m.group(i)) for i in (1, 2, 3, 4))
    try:
        target = datetime(now.year, mo, d, h, mi)
        if target <= now:
            target = target.replace(year=now.year + 1)
        return target
    except ValueError:
        return None


@router.callback_query(F.data.startswith("notes:"))
async def notes_list(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    e = await get_elderly(eid)
    if not e:
        await cb.answer("Не найден", show_alert=True)
        return
    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return
    if not await can_edit_family_data(e.family_id, user.id):
        await cb.answer("У вас нет прав на изменение.", show_alert=True)
        return
    notes = await list_notes_for_elderly(eid, only_pending=True)
    if not notes:
        text = (
            "📝 Заметки — " + e.name + "\n\n"
            "Пока пусто. Здесь можно создать напоминание для близкого: "
            "например, «приём у кардиолога 15.11 14:30»."
        )
    else:
        text = "📝 Заметки — " + e.name + "\n\nВсего: " + str(len(notes))
    await cb.message.edit_text(text, reply_markup=kb_notes_menu(eid, notes))
    await cb.answer()


@router.callback_query(F.data.startswith("note_add:"))
async def note_add_start(cb: CallbackQuery, state: FSMContext):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    e = await get_elderly(eid)
    if not e:
        await cb.answer("Не найден", show_alert=True)
        return
    user = await get_user_by_tg(cb.from_user.id)
    if not user or not await can_edit_family_data(e.family_id, user.id):
        await cb.answer("У вас нет прав на изменение.", show_alert=True)
        return
    await state.update_data(note_eid=eid)
    await state.set_state(NoteAdd.text)
    await cb.message.edit_text(
        "Введите текст заметки.\n\n"
        "Например: «Приём у кардиолога» или «Купить лекарства».\n\n"
        "Чтобы отменить — отправьте /cancel"
    )
    await cb.answer()


@router.message(NoteAdd.text, F.text, ~F.text.startswith("/"))
async def note_add_text(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if not txt or len(txt) > 200:
        await msg.answer("Текст должен быть от 1 до 200 символов.")
        return
    await state.update_data(note_text=txt)
    await state.set_state(NoteAdd.time)
    await msg.answer(
        "Когда напомнить?\n\n"
        "• <b>14:30</b> — сегодня или завтра в это время\n"
        "• <b>15.11 14:30</b> — конкретная дата\n\n"
        "Чтобы отменить — отправьте /cancel"
    )


@router.message(NoteAdd.time, F.text, ~F.text.startswith("/"))
async def note_add_time(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    target = _parse_time(txt)
    if not target:
        await msg.answer("Не понял дату. Примеры: 14:30 или 15.11 14:30")
        return
    data = await state.get_data()
    eid = data.get("note_eid")
    text = data.get("note_text", "")
    user = await get_user_by_tg(msg.from_user.id)
    n = await add_note(eid, text, target,
                       created_by=(user.id if user else None))
    await state.clear()
    when = target.strftime("%d.%m в %H:%M")
    await msg.answer(
        "📝 Заметка сохранена.\n\n"
        "Напоминание: " + text + "\nКогда: " + when + "\n\n"
        "Мы напомним близкому в это время."
    )
    await schedule_note(msg.bot, n.id)


@router.callback_query(F.data.startswith("note_view:"))
async def note_view(cb: CallbackQuery):
    try:
        nid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    n = await get_note(nid)
    if not n:
        await cb.answer("Заметка удалена", show_alert=True)
        return
    e = await get_elderly(n.elderly_id)
    text = (
        "📝 Заметка\n\n"
        "Текст: " + n.text + "\n"
        "Когда: " + n.remind_at.strftime("%d.%m.%Y в %H:%M") + "\n"
        "Статус: " + n.status
    )
    if n.feedback:
        fb = {"good": "✅ всё хорошо", "meh": "😐 так себе", "bad": "❌ не получилось"}
        text = text + "\nОбратная связь: " + fb.get(n.feedback, n.feedback)
    await cb.message.edit_text(
        text, reply_markup=kb_note_view(nid, n.elderly_id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("note_del:"))
async def note_del(cb: CallbackQuery):
    try:
        nid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    n = await get_note(nid)
    if not n:
        await cb.answer("Уже удалена", show_alert=True)
        return
    eid = n.elderly_id
    await delete_note(nid)
    await cb.answer("Удалено")
    cb2 = cb.model_copy(update={"data": "notes:" + str(eid)})
    await notes_list(cb2)


@router.callback_query(F.data.startswith("note_fb:"))
async def note_feedback(cb: CallbackQuery):
    parts = cb.data.split(":")
    if len(parts) != 3:
        await cb.answer()
        return
    try:
        nid = int(parts[1])
    except ValueError:
        await cb.answer()
        return
    fb = parts[2]
    n = await get_note(nid)
    if not n:
        await cb.answer("Заметка удалена", show_alert=True)
        return
    if n.status == "done":
        await cb.answer("Уже отвечено", show_alert=True)
        return
    await mark_note_done(nid, feedback=fb)
    labels = {"good": "всё хорошо ✅", "meh": "так себе 😐", "bad": "не получилось ❌"}
    await cb.message.edit_text(
        "Спасибо! Передали близким: " + labels.get(fb, fb)
    )
    await cb.answer()
    e = await get_elderly(n.elderly_id)
    if e:
        from app.services.notify import notify_note_feedback
        text = "📝 " + e.name + " (" + n.text + "): " + labels.get(fb, fb)
        await notify_note_feedback(cb.bot, e, text)


@router.message(NoteAdd.text, F.text.startswith("/cancel"))
async def note_cancel1(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("Отменено.")


@router.message(NoteAdd.time, F.text.startswith("/cancel"))
async def note_cancel2(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("Отменено.")