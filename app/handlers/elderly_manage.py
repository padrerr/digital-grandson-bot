import logging
import re
from datetime import datetime

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, FSInputFile
from sqlalchemy import delete as sqldelete

from app.db import (
    Session, Elderly, Routine, Event, WellbeingLog, Measurement,
    get_user_by_tg, get_user_family, get_elderly,
    list_family_elderly,
    add_routine, get_routines, get_routine, update_routine,
    delete_routine, delete_all_routines,
    set_quiet, is_quiet_hours, set_birthday,
    create_custom_template, list_custom_templates, get_custom_template,
    delete_custom_template, custom_template_items,
    can_edit_family_data,
)
from app.keyboards import (
    kb_elderly_manage, kb_quiet_panel, kb_routine_menu, kb_routine_edit,
    kb_templates, kb_template_apply_mode, kb_choose_elderly,
    kb_family_menu, kb_elderly_panel, kb_birthday_panel,
    kb_measure_kind_pick, kb_clear_confirm,
    kb_custom_templates, kb_custom_template_apply,
)
from app.services import measurements as M
from app.scheduler import schedule_absolute_routines
from app.services.csv_export import export_history, cleanup
from app.templates import TEMPLATES

log = logging.getLogger(__name__)
router = Router()


class RoutineAdd(StatesGroup):
    title = State()
    time = State()


class RoutineRename(StatesGroup):
    name = State()


class RoutineRetime(StatesGroup):
    time = State()


class CheckinSet(StatesGroup):
    hour = State()


class QuietSet(StatesGroup):
    hours = State()


class BirthdaySet(StatesGroup):
    mm_dd = State()


class SaveTemplate(StatesGroup):
    name = State()


def _routine_list_text(e, routines):
    from app.services.formatting import format_when
    text = "Распорядок — " + e.name + "\n\n"
    for r in routines:
        prefix = "🩺 " if r.measure_kind else "• "
        when = format_when(r.mode, r.offset_min, r.hour, r.minute)
        text = text + prefix + r.title + " — " + when + "\n"
    if not routines:
        text = text + "Пока пусто."
    return text


async def _check_edit(cb: CallbackQuery, elderly_id: int) -> bool:
    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return False
    e = await get_elderly(elderly_id)
    if not e:
        await cb.answer("Не найден", show_alert=True)
        return False
    if not await can_edit_family_data(e.family_id, user.id):
        await cb.answer("У вас нет прав на изменение.", show_alert=True)
        return False
    return True


async def _show_rt_menu(cb, elderly_id):
    user = await get_user_by_tg(cb.from_user.id)
    e = await get_elderly(elderly_id)
    if not e:
        return
    can_edit = False
    if user:
        can_edit = await can_edit_family_data(e.family_id, user.id)
    routines = await get_routines(elderly_id)
    await cb.message.edit_text(
        _routine_list_text(e, routines),
        reply_markup=kb_routine_menu(elderly_id, routines, can_edit=can_edit),
    )


def _routine_to_item(r):
    return {
        "title": r.title,
        "mode": r.mode,
        "offset_min": r.offset_min,
        "hour": r.hour,
        "minute": r.minute,
        "measure_kind": r.measure_kind,
    }


@router.callback_query(F.data.startswith("eld:"))
async def elderly_panel(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return
    e = await get_elderly(eid)
    if not e:
        await cb.answer("Не найден", show_alert=True)
        return
    can_edit = await can_edit_family_data(e.family_id, user.id)
    from app.db import get_member_role
    role = await get_member_role(e.family_id, user.id)
    owner = (role == "owner")
    status = "🟢 активен" if e.active else "⏸ на паузе"
    linked = "✅ подключён" if e.user_id else "⏳ ждёт приглашения"
    quiet = "🌙 вкл" if e.quiet_enabled else "☀️ выкл"
    text = (
        e.name + "\n"
        "Статус: " + status + "\n"
        "Подключён: " + linked + "\n"
        "Тихие часы: " + quiet
    )
    if not can_edit:
        text = text + "\n\n👁 Только просмотр"
    await cb.message.edit_text(
        text, reply_markup=kb_elderly_manage(eid, can_edit, owner),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("invite_eld:"))
async def invite_elderly(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    e = await get_elderly(eid)
    bot_username = (await cb.bot.me()).username
    link = "https://t.me/" + bot_username + "?start=eld_" + e.invite_code
    text = (
        "Ссылка для " + e.name + ":\n" + link + "\n\n"
        "Открывает сам близкий со своего Telegram."
    )
    await cb.message.edit_text(text, reply_markup=kb_elderly_manage(eid, True, True))
    await cb.answer()


@router.callback_query(F.data.startswith("toggle:"))
async def toggle_elderly(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    async with Session() as s:
        e = await s.get(Elderly, eid)
        if not e:
            await cb.answer("Не найден", show_alert=True)
            return
        e.active = not e.active
        await s.commit()
    await cb.answer("Обновлено")
    await elderly_panel(cb)


@router.callback_query(F.data.startswith("del_eld:"))
async def delete_elderly(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return
    e = await get_elderly(eid)
    if not e:
        await cb.answer("Не найден", show_alert=True)
        return
    from app.db import get_member_role
    if await get_member_role(e.family_id, user.id) != "owner":
        await cb.answer("Только владелец может удалять.", show_alert=True)
        return
    async with Session() as s:
        await s.execute(sqldelete(Routine).where(Routine.elderly_id == eid))
        await s.execute(sqldelete(Event).where(Event.elderly_id == eid))
        await s.execute(sqldelete(WellbeingLog).where(WellbeingLog.elderly_id == eid))
        await s.execute(sqldelete(Measurement).where(Measurement.elderly_id == eid))
        ee = await s.get(Elderly, eid)
        if ee:
            await s.delete(ee)
        await s.commit()
    await cb.answer("Удалён", show_alert=True)
    elderly = await list_family_elderly(e.family_id)
    text = "❤️ Близкие под нашей заботой\n\nВсего: " + str(len(elderly))
    await cb.message.edit_text(text, reply_markup=kb_elderly_panel(elderly))


@router.callback_query(F.data.startswith("checkin:"))
async def checkin_edit(cb: CallbackQuery, state: FSMContext):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    e = await get_elderly(eid)
    await state.update_data(checkin_eid=eid)
    await state.set_state(CheckinSet.hour)
    await cb.message.edit_text(
        "Сейчас время чек-ина: " + str(e.checkin_hour) + ":00\n"
        "Введите новый час (0–23):"
    )
    await cb.answer()


@router.message(CheckinSet.hour, F.text, ~F.text.startswith("/"))
async def checkin_set(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    try:
        h = int(txt)
        assert 0 <= h < 24
    except (ValueError, AssertionError):
        await msg.answer("Введите число 0–23.")
        return
    data = await state.get_data()
    async with Session() as s:
        e = await s.get(Elderly, data.get("checkin_eid"))
        if e:
            e.checkin_hour = h
            await s.commit()
    await state.clear()
    await msg.answer("Чек-ин установлен на " + str(h) + ":00",
                     reply_markup=kb_family_menu())


@router.callback_query(F.data.startswith("quiet:"))
async def quiet_panel(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    e = await get_elderly(eid)
    if not e:
        await cb.answer("Не найден", show_alert=True)
        return
    is_q = is_quiet_hours(e, datetime.now())
    status = "🌙 включены" if e.quiet_enabled else "☀️ выключены"
    now_txt = "сейчас тихо" if is_q else "сейчас активно"
    text = (
        "🌙 Тихие часы — " + e.name + "\n\n"
        "Статус: " + status + "\n"
        "Период: " + f"{e.quiet_start:02d}:00 – {e.quiet_end:02d}:00" + "\n"
        "Сейчас: " + now_txt + "\n\n"
        "Ночные уведомления родственникам не отправляются. "
        "Критические тревоги приходят всегда."
    )
    await cb.message.edit_text(
        text,
        reply_markup=kb_quiet_panel(eid, e.quiet_enabled, e.quiet_start,
                                    e.quiet_end, is_q),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("quiet_toggle:"))
async def quiet_toggle(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    e = await get_elderly(eid)
    await set_quiet(eid, enabled=not e.quiet_enabled)
    await cb.answer("Переключено")
    await quiet_panel(cb)


@router.callback_query(F.data.startswith("quiet_time:"))
async def quiet_time(cb: CallbackQuery, state: FSMContext):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    e = await get_elderly(eid)
    await state.update_data(quiet_eid=eid)
    await state.set_state(QuietSet.hours)
    text = (
        "Текущий период: " + f"{e.quiet_start:02d}:00 – {e.quiet_end:02d}:00" + "\n\n"
        "Введите новый период в формате 23-7."
    )
    await cb.message.edit_text(text)
    await cb.answer()


@router.message(QuietSet.hours, F.text, ~F.text.startswith("/"))
async def quiet_time_set(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    txt = txt.replace(":", "").replace("–", "-").replace("—", "-")
    m = re.match(r"^(\d{1,2})\s*-\s*(\d{1,2})$", txt)
    if not m:
        await msg.answer("Не понял. Пример: 23-7")
        return
    s_h, e_h = int(m.group(1)), int(m.group(2))
    if not (0 <= s_h < 24 and 0 <= e_h < 24):
        await msg.answer("Часы от 0 до 23. Пример: 23-7")
        return
    data = await state.get_data()
    await set_quiet(data.get("quiet_eid"), start=s_h, end=e_h)
    await state.clear()
    text = "Тихие часы установлены: " + f"{s_h:02d}:00 – {e_h:02d}:00"
    await msg.answer(text, reply_markup=kb_family_menu())


@router.callback_query(F.data.startswith("bday:"))
async def birthday_panel(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    e = await get_elderly(eid)
    if not e:
        await cb.answer("Не найден", show_alert=True)
        return
    cur = e.birthday
    if cur:
        text = "🎂 День рождения — " + e.name + "\n\nСейчас: " + cur
    else:
        text = "🎂 День рождения — " + e.name + "\n\nДата не задана."
    text = text + "\n\nРодственники получат напоминание за день и в сам день."
    await cb.message.edit_text(text, reply_markup=kb_birthday_panel(eid, cur))
    await cb.answer()


@router.callback_query(F.data.startswith("bday_set:"))
async def birthday_set_start(cb: CallbackQuery, state: FSMContext):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    await state.update_data(bday_eid=eid)
    await state.set_state(BirthdaySet.mm_dd)
    await cb.message.edit_text(
        "Введите дату в формате MM-DD, например 07-15 для 15 июля."
    )
    await cb.answer()


@router.message(BirthdaySet.mm_dd, F.text, ~F.text.startswith("/"))
async def birthday_set_finish(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})$", txt)
    if not m:
        await msg.answer("Не понял. Пример: 07-15")
        return
    mm, dd = int(m.group(1)), int(m.group(2))
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        await msg.answer("Проверьте месяц и день. Пример: 07-15")
        return
    mm_dd = f"{mm:02d}-{dd:02d}"
    data = await state.get_data()
    await set_birthday(data.get("bday_eid"), mm_dd)
    await state.clear()
    await msg.answer("🎂 Дата сохранена: " + mm_dd,
                     reply_markup=kb_family_menu())


@router.callback_query(F.data.startswith("bday_clear:"))
async def birthday_clear(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    await set_birthday(eid, None)
    await cb.answer("Убрано", show_alert=True)
    await birthday_panel(cb)


@router.callback_query(F.data.startswith("csv:"))
async def csv_export(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    e = await get_elderly(eid)
    if not e:
        await cb.answer("Не найден", show_alert=True)
        return
    await cb.answer("Готовлю файл…")
    result = await export_history(eid)
    if not result:
        await cb.message.answer("Не удалось собрать данные.")
        return
    tmp_path, filename, count = result
    caption = "📤 История — " + e.name + "\nЗаписей: " + str(count)
    try:
        await cb.message.answer_document(
            FSInputFile(tmp_path, filename=filename),
            caption=caption,
        )
    except Exception as ex:
        log.warning("CSV send failed: %s", ex)
        await cb.message.answer("Не удалось отправить файл.")
    finally:
        cleanup(tmp_path)


@router.callback_query(F.data.startswith("rt_menu:"))
async def rt_menu(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    await _show_rt_menu(cb, eid)
    await cb.answer()


@router.callback_query(F.data.startswith("rt_clear:"))
async def rt_clear(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    e = await get_elderly(eid)
    routines = await get_routines(eid)
    text = (
        "🗑 Очистить весь распорядок — " + e.name + "?\n\n"
        "Будет удалено задач: " + str(len(routines)) + ".\n"
        "Действие нельзя отменить."
    )
    await cb.message.edit_text(text, reply_markup=kb_clear_confirm(eid))
    await cb.answer()


@router.callback_query(F.data.startswith("rt_clear_yes:"))
async def rt_clear_yes(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    await delete_all_routines(eid)
    await cb.answer("Очищено", show_alert=True)
    await _show_rt_menu(cb, eid)


@router.callback_query(F.data.startswith("rt_add:"))
async def rt_add(cb: CallbackQuery, state: FSMContext):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    await state.update_data(rt_eid=eid, rt_measure=None)
    await state.set_state(RoutineAdd.title)
    await cb.message.edit_text("Название задачи (например: «Поел», «Выпил таблетки»):")
    await cb.answer()


@router.callback_query(F.data.startswith("rt_add_measure:"))
async def rt_add_measure(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    await cb.message.edit_text(
        "Что замеряем?",
        reply_markup=kb_measure_kind_pick(eid),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("rt_measure_kind:"))
async def rt_measure_kind(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    if len(parts) != 3:
        await cb.answer()
        return
    _, eid_s, kind = parts
    if kind not in M.KINDS:
        await cb.answer("Неизвестный вид замера", show_alert=True)
        return
    try:
        eid = int(eid_s)
    except ValueError:
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    await state.update_data(rt_eid=eid, rt_measure=kind)
    await state.set_state(RoutineAdd.title)
    default_title = "Замер " + M.label(kind)
    text = (
        "Название задачи. Можно оставить по умолчанию:\n"
        "«" + default_title + "»\n\n"
        "Или напишите своё."
    )
    await cb.message.edit_text(text)
    await cb.answer()


@router.message(RoutineAdd.title, F.text, ~F.text.startswith("/"))
async def rt_add_title(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    data = await state.get_data()
    kind = data.get("rt_measure")
    if not txt:
        if kind:
            txt = "Замер " + M.label(kind)
        else:
            await msg.answer("Пожалуйста, напишите текстом.")
            return
    if len(txt) > 100:
        await msg.answer("Название задачи слишком длинное (максимум 100 символов).")
        return
    await state.update_data(rt_title=txt)
    await state.set_state(RoutineAdd.time)
    if kind:
        unit = M.unit(kind)
        example = M.example(kind)
        text = (
            "Во сколько напоминать?\n"
            "• Время в формате 08:00\n"
            "• Или число минут — 60 (через час после пробуждения)\n\n"
            "При срабатывании я попрошу ввести значение " + M.label(kind) +
            " (" + unit + "), например: " + example
        )
        await msg.answer(text)
    else:
        await msg.answer(
            "Когда напоминать?\n"
            "• Время в формате 08:00\n"
            "• Или число минут — 60"
        )


@router.message(RoutineAdd.time, F.text, ~F.text.startswith("/"))
async def rt_add_time(msg: Message, state: FSMContext):
    data = await state.get_data()
    eid = data.get("rt_eid")
    title = data.get("rt_title", "")
    kind = data.get("rt_measure")
    txt = (msg.text or "").strip()
    if ":" in txt:
        try:
            h, m = txt.split(":")
            h, m = int(h), int(m)
            assert 0 <= h < 24 and 0 <= m < 60
        except (ValueError, AssertionError):
            await msg.answer("Не понял. Пример: 08:00")
            return
        await add_routine(eid, title, mode="absolute", hour=h, minute=m,
                          measure_kind=kind)
    else:
        try:
            off = int(txt)
            assert 0 <= off <= 24 * 60
        except (ValueError, AssertionError):
            await msg.answer("Не понял. Введите время (08:00) или минуты.")
            return
        await add_routine(eid, title, mode="wake_offset", offset_min=off,
                          measure_kind=kind)
    await state.clear()
    await schedule_absolute_routines(msg.bot)
    e = await get_elderly(eid)
    routines = await get_routines(eid)
    await msg.answer(_routine_list_text(e, routines),
                     reply_markup=kb_routine_menu(eid, routines))


@router.callback_query(F.data.startswith("rt_edit:"))
async def rt_edit(cb: CallbackQuery):
    try:
        rid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    r = await get_routine(rid)
    if not r:
        await cb.answer("Запись уже удалена", show_alert=True)
        return
    if not await _check_edit(cb, r.elderly_id):
        return
    if r.mode == "wake_offset":
        when = "через " + str(r.offset_min) + " мин после пробуждения"
    else:
        when = "в " + f"{r.hour:02d}:{r.minute:02d}"
    text = r.title + "\nКогда: " + when
    if r.measure_kind:
        text = text + "\nТип замера: " + M.label(r.measure_kind)
    await cb.message.edit_text(text, reply_markup=kb_routine_edit(rid))
    await cb.answer()


@router.callback_query(F.data.startswith("rt_del:"))
async def rt_del(cb: CallbackQuery):
    try:
        rid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    r = await get_routine(rid)
    if not r:
        await cb.answer("Уже удалено", show_alert=True)
        return
    if not await _check_edit(cb, r.elderly_id):
        return
    eid = r.elderly_id
    await delete_routine(rid)
    await cb.answer("Удалено")
    await _show_rt_menu(cb, eid)


@router.callback_query(F.data.startswith("rt_back:"))
async def rt_back(cb: CallbackQuery):
    try:
        rid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    r = await get_routine(rid)
    if not r:
        await cb.answer("Запись удалена", show_alert=True)
        return
    await _show_rt_menu(cb, r.elderly_id)
    await cb.answer()


@router.callback_query(F.data.startswith("rt_rename:"))
async def rt_rename(cb: CallbackQuery, state: FSMContext):
    try:
        rid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    r = await get_routine(rid)
    if not r:
        await cb.answer("Запись удалена", show_alert=True)
        return
    if not await _check_edit(cb, r.elderly_id):
        return
    await state.update_data(rt_rid=rid)
    await state.set_state(RoutineRename.name)
    await cb.message.edit_text("Новое название:")
    await cb.answer()


@router.message(RoutineRename.name, F.text, ~F.text.startswith("/"))
async def rt_rename_done(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if not txt:
        await msg.answer("Пожалуйста, напишите текстом.")
        return
    if len(txt) > 100:
        await msg.answer("Название задачи слишком длинное (максимум 100 символов).")
        return
    data = await state.get_data()
    rid = data.get("rt_rid")
    r = await get_routine(rid)
    if not r:
        await state.clear()
        await msg.answer("Запись уже удалена.", reply_markup=kb_family_menu())
        return
    eid = r.elderly_id
    await update_routine(rid, title=txt)
    await state.clear()
    e = await get_elderly(eid)
    routines = await get_routines(eid)
    await msg.answer(_routine_list_text(e, routines),
                     reply_markup=kb_routine_menu(eid, routines))


@router.callback_query(F.data.startswith("rt_retime:"))
async def rt_retime(cb: CallbackQuery, state: FSMContext):
    try:
        rid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    r = await get_routine(rid)
    if not r:
        await cb.answer("Запись удалена", show_alert=True)
        return
    if not await _check_edit(cb, r.elderly_id):
        return
    await state.update_data(rt_rid=rid)
    await state.set_state(RoutineRetime.time)
    await cb.message.edit_text(
        "Новое время:\n"
        "• 08:00 — жёсткое время\n"
        "• 60 — через 60 минут после пробуждения"
    )
    await cb.answer()


@router.message(RoutineRetime.time, F.text, ~F.text.startswith("/"))
async def rt_retime_done(msg: Message, state: FSMContext):
    data = await state.get_data()
    rid = data.get("rt_rid")
    r = await get_routine(rid)
    if not r:
        await state.clear()
        await msg.answer("Запись уже удалена.", reply_markup=kb_family_menu())
        return
    eid = r.elderly_id
    txt = (msg.text or "").strip()
    if ":" in txt:
        try:
            h, m = txt.split(":")
            h, m = int(h), int(m)
            assert 0 <= h < 24 and 0 <= m < 60
            await update_routine(rid, mode="absolute", hour=h, minute=m)
        except (ValueError, AssertionError):
            await msg.answer("Формат ЧЧ:ММ.")
            return
    else:
        try:
            off = int(txt)
            assert 0 <= off <= 24 * 60
            await update_routine(rid, mode="wake_offset", offset_min=off)
        except (ValueError, AssertionError):
            await msg.answer("Введите число минут (0–1440).")
            return
    await state.clear()
    e = await get_elderly(eid)
    routines = await get_routines(eid)
    await msg.answer(_routine_list_text(e, routines),
                     reply_markup=kb_routine_menu(eid, routines))


@router.callback_query(F.data == "tpl_choose")
async def tpl_choose(cb: CallbackQuery):
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
    elderly = await list_family_elderly(f.id)
    if not elderly:
        await cb.message.edit_text("В семье ещё нет близких.",
                                   reply_markup=kb_elderly_panel([]))
        await cb.answer()
        return
    if len(elderly) == 1:
        e = elderly[0]
        routines = await get_routines(e.id)
        await cb.message.edit_text(
            "Выберите шаблон:",
            reply_markup=kb_templates(e.id, has_routines=bool(routines)),
        )
        await cb.answer()
        return
    await cb.message.edit_text(
        "К кому применить шаблон?",
        reply_markup=kb_choose_elderly(elderly, prefix="tpl"),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("tpl:"))
async def tpl_menu(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    e = await get_elderly(eid)
    routines = await get_routines(eid)
    await cb.message.edit_text(
        "Выберите шаблон:",
        reply_markup=kb_templates(eid, has_routines=bool(routines)),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("tpl_my:"))
async def tpl_my(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    user = await get_user_by_tg(cb.from_user.id)
    uf = await get_user_family(user.id)
    if not uf:
        await cb.answer()
        return
    f, _ = uf
    templates = await list_custom_templates(f.id)
    if not templates:
        text = (
            "📂 Мои шаблоны\n\n"
            "Пока пусто. Чтобы сохранить текущий распорядок как шаблон, "
            "откройте распорядок близкого и нажмите "
            "«💾 Сохранить текущий как шаблон»."
        )
        await cb.message.edit_text(text, reply_markup=kb_templates(eid, has_routines=True))
        await cb.answer()
        return
    text = "📂 Мои шаблоны (" + str(len(templates)) + "):"
    await cb.message.edit_text(text, reply_markup=kb_custom_templates(eid, templates))
    await cb.answer()


@router.callback_query(F.data.startswith("tpl_save:"))
async def tpl_save_start(cb: CallbackQuery, state: FSMContext):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    e = await get_elderly(eid)
    routines = await get_routines(eid)
    if not routines:
        await cb.answer("Распорядок пуст — нечего сохранять.", show_alert=True)
        return
    await state.update_data(save_tpl_eid=eid)
    await state.set_state(SaveTemplate.name)
    await cb.message.edit_text(
        "Введите название для нового шаблона.\n\n"
        "Задач будет сохранено: " + str(len(routines)) + "."
    )
    await cb.answer()


@router.message(SaveTemplate.name, F.text, ~F.text.startswith("/"))
async def tpl_save_finish(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if not txt or len(txt) > 60:
        await msg.answer("Название должно быть от 1 до 60 символов.")
        return
    data = await state.get_data()
    eid = data.get("save_tpl_eid")
    user = await get_user_by_tg(msg.from_user.id)
    if not user:
        await state.clear()
        return
    uf = await get_user_family(user.id)
    if not uf:
        await state.clear()
        await msg.answer("Семья не найдена.")
        return
    f, _ = uf
    routines = await get_routines(eid)
    if not routines:
        await state.clear()
        await msg.answer("Распорядок пуст.")
        return
    items = [_routine_to_item(r) for r in routines]
    await create_custom_template(f.id, txt, items)
    await state.clear()
    await msg.answer(
        "💾 Шаблон сохранён: «" + txt + "»\n"
        "Задач: " + str(len(items)) + ".\n\n"
        "Найти его можно в «🎁 Шаблоны» → «📂 Мои шаблоны».",
        reply_markup=kb_family_menu(),
    )


@router.callback_query(F.data.startswith("tpl_custom_apply:"))
async def tpl_custom_apply(cb: CallbackQuery):
    parts = cb.data.split(":")
    if len(parts) != 3:
        await cb.answer()
        return
    try:
        tid = int(parts[1])
        eid = int(parts[2])
    except ValueError:
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    t = await get_custom_template(tid)
    if not t:
        await cb.answer("Шаблон не найден", show_alert=True)
        return
    items = custom_template_items(t)
    if not items:
        await cb.answer("Шаблон пуст", show_alert=True)
        return
    existing = await get_routines(eid)
    text = "📋 Шаблон «" + t.name + "»:\n\n"
    for it in items:
        if it.get("mode") == "wake_offset":
            when = "через " + str(it.get("offset_min", 0)) + " мин"
        else:
            when = f"{int(it.get('hour', 8)):02d}:{int(it.get('minute', 0)):02d}"
        prefix = "🩺 " if it.get("measure_kind") else "• "
        text = text + prefix + str(it.get("title", "")) + " — " + when + "\n"
    if existing:
        text = text + "\n⚠️ У близкого уже есть " + str(len(existing)) + " задач."
    else:
        text = text + "\nЗадач будет добавлено: " + str(len(items)) + "."
    await cb.message.edit_text(
        text,
        reply_markup=kb_custom_template_apply(tid, eid, has_routines=bool(existing)),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("tpl_custom_mode:"))
async def tpl_custom_mode(cb: CallbackQuery):
    parts = cb.data.split(":")
    if len(parts) != 4:
        await cb.answer()
        return
    try:
        tid = int(parts[1])
        eid = int(parts[2])
    except ValueError:
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    mode = parts[3]
    t = await get_custom_template(tid)
    if not t:
        await cb.answer("Шаблон не найден", show_alert=True)
        return
    items = custom_template_items(t)
    if mode == "replace":
        await delete_all_routines(eid)
    for it in items:
        if it.get("mode") == "wake_offset":
            await add_routine(eid, str(it.get("title", "")),
                              mode="wake_offset",
                              offset_min=int(it.get("offset_min", 30)),
                              measure_kind=it.get("measure_kind"))
        else:
            await add_routine(eid, str(it.get("title", "")),
                              mode="absolute",
                              hour=int(it.get("hour", 8)),
                              minute=int(it.get("minute", 0)),
                              measure_kind=it.get("measure_kind"))
    await schedule_absolute_routines(cb.bot)
    await cb.answer("Готово")
    await _show_rt_menu(cb, eid)


@router.callback_query(F.data.startswith("tpl_custom_del:"))
async def tpl_custom_del(cb: CallbackQuery):
    parts = cb.data.split(":")
    if len(parts) != 3:
        await cb.answer()
        return
    try:
        tid = int(parts[1])
        eid = int(parts[2])
    except ValueError:
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    await delete_custom_template(tid)
    await cb.answer("Шаблон удалён", show_alert=True)
    user = await get_user_by_tg(cb.from_user.id)
    uf = await get_user_family(user.id)
    if not uf:
        return
    templates = await list_custom_templates(uf[0].id)
    if not templates:
        await cb.message.edit_text("📂 Мои шаблоны\n\nПока пусто.",
                                   reply_markup=kb_templates(eid, has_routines=True))
        return
    await cb.message.edit_text(
        "📂 Мои шаблоны (" + str(len(templates)) + "):",
        reply_markup=kb_custom_templates(eid, templates),
    )


@router.callback_query(F.data.startswith("tpl_apply:"))
async def tpl_apply(cb: CallbackQuery):
    parts = cb.data.split(":")
    if len(parts) != 3:
        await cb.answer()
        return
    _, eid_s, key = parts
    if key not in TEMPLATES:
        await cb.answer("Неизвестный шаблон", show_alert=True)
        return
    try:
        eid = int(eid_s)
    except ValueError:
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    tpl = TEMPLATES[key]
    text = tpl["name"] + "\n\n"
    for it in tpl["items"]:
        prefix = "🩺 " if it.get("measure_kind") else "• "
        text = text + prefix + it["title"] + " — " + f"{it['hour']:02d}:{it['minute']:02d}" + "\n"
    existing = await get_routines(eid)
    if existing:
        text = text + "\n⚠️ У близкого уже есть " + str(len(existing)) + " задач."
    else:
        text = text + "\nЗадач будет добавлено: " + str(len(tpl["items"])) + "."
    await cb.message.edit_text(
        text + "\nПрименить как?",
        reply_markup=kb_template_apply_mode(eid, key, has_routines=bool(existing)),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("tpl_mode:"))
async def tpl_apply_mode(cb: CallbackQuery):
    parts = cb.data.split(":")
    if len(parts) != 4:
        await cb.answer()
        return
    _, eid_s, key, mode = parts
    if key not in TEMPLATES:
        await cb.answer("Неизвестный шаблон", show_alert=True)
        return
    try:
        eid = int(eid_s)
    except ValueError:
        await cb.answer()
        return
    if not await _check_edit(cb, eid):
        return
    tpl = TEMPLATES[key]
    if mode == "replace":
        await delete_all_routines(eid)
    for it in tpl["items"]:
        await add_routine(eid, it["title"], mode="absolute",
                          hour=it["hour"], minute=it["minute"],
                          measure_kind=it.get("measure_kind"))
    await cb.answer("Применено")
    await schedule_absolute_routines(cb.bot)
    await _show_rt_menu(cb, eid)