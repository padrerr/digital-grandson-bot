import logging
import random
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, desc

from app.db import (
    Session, Event,
    get_user_by_tg, get_elderly_by_user, get_elderly,
    get_routines, get_routine, get_event, set_event_status,
    set_wake, log_wellbeing, list_family_members, add_measurement,
    is_quiet_hours,
)
from app.keyboards import (
    kb_elderly_menu, kb_wellbeing, kb_routine_event, kb_problem_pick,
)
from app.scheduler import schedule_day_for_elderly
from app.services.notify import notify_task_action, notify_wellbeing
from app.services import measurements as M

log = logging.getLogger(__name__)
router = Router()


class MeasureInput(StatesGroup):
    waiting_value = State()


class ProblemOther(StatesGroup):
    waiting_text = State()


REPLY_TEXTS = {
    "good": "Спасибо! Рад за вас.",
    "ok": "Понял. Если станет хуже — напишите.",
    "bad": "Пожалуйста, позвоните 103 или 112, если вам плохо.",
    "help": "Позвоните 112 прямо сейчас.",
    "critical": "Пожалуйста, срочно позвоните 112 или 103!",
}

PROBLEMS = {
    "head": {
        "label": "болит голова",
        "reply": "Мы сообщили близким, что у вас болит голова. "
                 "Если боль сильная — позвоните 103.",
        "family": "🤕 {name} сообщает: болит голова",
        "critical": False,
    },
    "heart": {
        "label": "болит сердце",
        "reply": "Мы сообщили близким. Если боль сильная или "
                 "отдаёт в руку — срочно позвоните 103 или 112!",
        "family": "🚨 {name} сообщает: БОЛИТ СЕРДЦЕ. Позвоните срочно!",
        "critical": True,
    },
    "breath": {
        "label": "тяжело дышать",
        "reply": "Мы сообщили близким. Если тяжело дышать — "
                 "срочно позвоните 103 или 112!",
        "family": "🚨 {name} сообщает: ТЯЖЕЛО ДЫШАТЬ. Позвоните срочно!",
        "critical": True,
    },
    "nausea": {
        "label": "тошнит",
        "reply": "Мы сообщили близким, что вас тошнит.",
        "family": "🤢 {name} сообщает: тошнит",
        "critical": False,
    },
    "dizzy": {
        "label": "головокружение",
        "reply": "Мы сообщили близким о головокружении. "
                 "Попробуйте присесть и отдохнуть.",
        "family": "💫 {name} сообщает: головокружение",
        "critical": False,
    },
    "stomach": {
        "label": "болит живот",
        "reply": "Мы сообщили близким, что у вас болит живот.",
        "family": "🤍 {name} сообщает: болит живот",
        "critical": False,
    },
    "weak": {
        "label": "слабость",
        "reply": "Мы сообщили близким о слабости. "
                 "Полежите, отдохните, выпейте воды.",
        "family": "🥱 {name} сообщает: слабость",
        "critical": False,
    },
}

MORNING_WISHES = [
    "Пусть день пройдёт спокойно и хорошо 🌷",
    "Желаю вам хорошего дня и добрых новостей ☀️",
    "Пусть сегодня всё будет легко и радостно 🌻",
    "Хорошего вам утра и приятного дня 🌸",
    "Пусть день принесёт что-то приятное 🌞",
]


async def _safe_edit(cb: CallbackQuery, text: str, remove_markup: bool = True):
    """
    Безопасно редактирует сообщение.
    Не падает, если сообщение уже неактуально, удалено или
    Telegram считает, что «ничего не изменилось».
    """
    try:
        await cb.message.edit_text(text)
    except Exception as ex:
        err = str(ex).lower()
        if "message is not modified" in err:
            # текст такой же — это не ошибка
            pass
        elif "message to edit not found" in err or "message can't be edited" in err:
            # сообщение старое/удалено — пробуем отправить новое
            try:
                await cb.message.answer(text)
            except Exception:
                pass
        else:
            log.warning("safe_edit edit_text failed: %s", ex)
            try:
                await cb.message.answer(text)
            except Exception:
                pass
        return
    if remove_markup:
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception as ex:
            # не критично, клавиатура могла уже исчезнуть
            err = str(ex).lower()
            if "message is not modified" not in err and "not found" not in err:
                log.debug("safe_edit edit_reply_markup failed: %s", ex)


async def apply_wellbeing_level(bot: Bot, elderly, level: str,
                                reply_fn, source: str = "button",
                                log_text: str = ""):
    async with Session() as s:
        r = await s.execute(
            select(Event).where(
                Event.elderly_id == elderly.id,
                Event.kind == "wellbeing",
            ).order_by(desc(Event.created_at)).limit(1)
        )
        ev = r.scalars().first()
        if ev:
            ev.status = level
            await s.commit()
    await log_wellbeing(elderly.id, log_text or level, level, source=source)
    await reply_fn(REPLY_TEXTS.get(level, "Понял."))
    if level in ("bad", "help", "critical"):
        await notify_wellbeing(bot, elderly, level)


@router.message(F.text == "☀️ Я проснулся")
async def woke_up_msg(msg: Message):
    user = await get_user_by_tg(msg.from_user.id)
    if not user:
        return
    e = await get_elderly_by_user(user.id)
    if not e:
        await msg.answer("Вы не подключены как близкий человек.")
        return
    await set_wake(e.id)
    greeting = ("Доброе утро, " + e.name + "! ") if e.name else "Доброе утро! "
    wish = random.choice(MORNING_WISHES)
    text = (greeting + wish + "\n\nРасписание на сегодня готово. "
            "Нажмите «📋 Мои задачи», чтобы посмотреть.")
    await msg.answer(text, reply_markup=kb_elderly_menu())
    await schedule_day_for_elderly(msg.bot, e.id)
    for u, _ in await list_family_members(e.family_id):
        try:
            await msg.bot.send_message(u.tg_id, "☀️ " + e.name + " проснулся(ась).")
        except Exception:
            pass


@router.callback_query(F.data == "woke_up")
async def woke_up_cb(cb: CallbackQuery):
    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return
    e = await get_elderly_by_user(user.id)
    if not e:
        await cb.answer("Не найден", show_alert=True)
        return
    await set_wake(e.id)
    wish = random.choice(MORNING_WISHES)
    await _safe_edit(cb, "Доброе утро! " + wish, remove_markup=False)
    await cb.answer()
    await schedule_day_for_elderly(cb.bot, e.id)


@router.message(F.text == "📋 Мои задачи")
async def my_tasks(msg: Message):
    user = await get_user_by_tg(msg.from_user.id)
    if not user:
        return
    e = await get_elderly_by_user(user.id)
    if not e:
        return
    routines = await get_routines(e.id)
    if not e.wake_at:
        text = "Сначала нажмите «☀️ Я проснулся»."
    else:
        lines = []
        for r in routines:
            if r.mode == "wake_offset":
                t = e.wake_at + timedelta(minutes=r.offset_min)
                lines.append("• " + t.strftime("%H:%M") + " — " + r.title)
            else:
                lines.append("• " + f"{r.hour:02d}:{r.minute:02d}" + " — " + r.title)
        if lines:
            text = "Ваши дела на сегодня:\n" + "\n".join(lines)
        else:
            text = "На сегодня дел нет."
    await msg.answer(text)


@router.message(F.text == "😊 Как я себя чувствую")
async def ask_wellbeing(msg: Message):
    await msg.answer("Как вы себя чувствуете?",
                     reply_markup=kb_wellbeing())


@router.callback_query(F.data.startswith("wb:"))
async def wellbeing_button(cb: CallbackQuery):
    parts = cb.data.split(":")
    if len(parts) != 2:
        await cb.answer()
        return
    level = parts[1]
    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return
    e = await get_elderly_by_user(user.id)
    if not e:
        await cb.answer()
        return

    async def edit_fn(text):
        await _safe_edit(cb, text, remove_markup=True)

    await apply_wellbeing_level(cb.bot, e, level, edit_fn,
                                source="button", log_text="кнопка: " + level)
    await cb.answer()


@router.message(F.text == "🩺 Сообщить о проблеме")
async def problem_start(msg: Message):
    await msg.answer(
        "Что вас беспокоит? Выберите из списка 👇",
        reply_markup=kb_problem_pick(),
    )


async def _notify_family_problem(bot: Bot, e, text: str, urgent: bool):
    if not urgent and is_quiet_hours(e, datetime.now()):
        return
    for u, _ in await list_family_members(e.family_id):
        try:
            await bot.send_message(u.tg_id, text)
        except Exception as ex:
            log.warning("notify problem failed: %s", ex)


@router.callback_query(F.data == "prob:cancel")
async def problem_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await _safe_edit(cb, "Хорошо, отменил.")
    await cb.answer()


@router.callback_query(F.data.startswith("prob:"))
async def problem_choice(cb: CallbackQuery, state: FSMContext):
    code = cb.data.split(":")[1]
    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer()
        return
    e = await get_elderly_by_user(user.id)
    if not e:
        await cb.answer()
        return

    if code == "other":
        await state.set_state(ProblemOther.waiting_text)
        await _safe_edit(
            cb,
            "Опишите, что вас беспокоит, одним сообщением.\n\n"
            "Чтобы отменить — отправьте /cancel",
        )
        await cb.answer()
        return

    info = PROBLEMS.get(code)
    if not info:
        await cb.answer()
        return

    await log_wellbeing(e.id, "жалоба: " + info["label"], "bad", source="button")
    await _safe_edit(cb, info["reply"])
    await cb.answer("Передали близким")

    from app.services.notify import notify_problem
    summary = info["family"].format(name=e.name)
    await notify_problem(cb.bot, e, summary, urgent=info["critical"])


@router.message(ProblemOther.waiting_text, F.text, ~F.text.startswith("/"))
async def problem_other_text(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if not txt:
        await msg.answer("Пожалуйста, напишите текстом.")
        return
    user = await get_user_by_tg(msg.from_user.id)
    if not user:
        await state.clear()
        return
    e = await get_elderly_by_user(user.id)
    if not e:
        await state.clear()
        return

    await log_wellbeing(e.id, "жалоба: " + txt, "bad", source="button")
    await state.clear()
    await msg.answer(
        "Мы сообщили близким. Они скоро свяжутся с вами.",
        reply_markup=kb_elderly_menu(),
    )
    from app.services.notify import notify_problem
    summary = "⚠️ " + e.name + " сообщает: " + txt
    await notify_problem(msg.bot, e, summary, urgent=False)


@router.message(ProblemOther.waiting_text, F.text.startswith("/cancel"))
async def problem_other_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("Отменено.", reply_markup=kb_elderly_menu())


async def _notify_call_request(bot: Bot, elderly_id: int):
    e = await get_elderly(elderly_id)
    if not e:
        return
    text = "📞 " + e.name + " хочет с вами поговорить. Позвоните, пожалуйста."
    for u, _ in await list_family_members(e.family_id):
        try:
            await bot.send_message(u.tg_id, text)
        except Exception:
            pass


@router.callback_query(F.data.startswith("rt:"))
async def routine_button(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    if len(parts) != 3:
        await cb.answer()
        return
    _, action, eid_s = parts
    try:
        ev_id = int(eid_s)
    except ValueError:
        await cb.answer()
        return

    ev = await get_event(ev_id)
    if not ev:
        await cb.answer("Задача уже неактуальна", show_alert=True)
        return

    if ev.status != "pending":
        await cb.answer("Уже обработано", show_alert=True)
        return

    r = await get_routine(ev.routine_id) if ev.routine_id else None
    title = r.title if r else "задача"
    e = await get_elderly(ev.elderly_id)
    name = (e.name if e else "").strip()
    is_measure = bool(r and r.measure_kind)

    if action == "done":
        if is_measure:
            await state.update_data(measure_event_id=ev.id,
                                    measure_kind=r.measure_kind)
            await state.set_state(MeasureInput.waiting_value)
            unit = M.unit(r.measure_kind)
            example = M.example(r.measure_kind)
            text = (
                "Введите значение " + M.label(r.measure_kind) +
                (" (" + unit + ")" if unit else "") + ".\n"
                "Например: " + example + "\n\n"
                "Чтобы отменить — отправьте /cancel"
            )
            await _safe_edit(cb, text)
        else:
            await set_event_status(ev.id, "done")
            if name:
                reply = "Молодец, " + name + "! Записал: «" + title + "»"
            else:
                reply = "Молодец! Записал: «" + title + "»"
            await _safe_edit(cb, reply)
            try:
                await notify_task_action(cb.bot, ev.elderly_id, title, "done")
            except Exception as ex:
                log.warning("notify_task_action failed: %s", ex)

    elif action == "skip":
        await set_event_status(ev.id, "skipped")
        await _safe_edit(cb, "Записал, что «" + title + "» пропущено.")
        try:
            await notify_task_action(cb.bot, ev.elderly_id, title, "skipped")
        except Exception as ex:
            log.warning("notify_task_action failed: %s", ex)

    elif action == "later":
        await set_event_status(ev.id, "pending")
        from app.scheduler import scheduler, routine_reminder
        scheduler.add_job(
            routine_reminder, "date",
            run_date=datetime.now() + timedelta(minutes=20),
            args=[cb.bot, ev.id],
            id="later_" + str(ev.id), replace_existing=True,
        )
        await _safe_edit(cb, "Хорошо, напомню через 20 минут.")

    elif action == "call":
        await _notify_call_request(cb.bot, ev.elderly_id)
        await _safe_edit(cb, "Передал близким, что вы хотите поговорить.")

    await cb.answer()


@router.message(MeasureInput.waiting_value, F.text, ~F.text.startswith("/"))
async def measure_value_input(msg: Message, state: FSMContext):
    data = await state.get_data()
    kind = data.get("measure_kind")
    ev_id = data.get("measure_event_id")
    if not kind or not ev_id:
        await state.clear()
        return

    txt = (msg.text or "").strip()
    value = M.validate(kind, txt)
    if not value:
        unit = M.unit(kind)
        example = M.example(kind)
        await msg.answer(
            "Не получилось распознать. Введите значение " +
            M.label(kind) + (" в " + unit if unit else "") +
            ".\nНапример: " + example
        )
        return

    ev = await get_event(ev_id)
    if not ev:
        await state.clear()
        await msg.answer("Задача уже неактуальна.")
        return

    e = await get_elderly(ev.elderly_id)

    await add_measurement(ev.elderly_id, kind, value, event_id=ev.id)
    await set_event_status(ev.id, "done")
    await state.clear()

    pretty_value = M.pretty(kind, value)
    await msg.answer(
        "Записал: " + M.label(kind) + " " + pretty_value + ". Спасибо!"
    )

    if e:
        text = ("📊 " + e.name + ": " + M.label(kind) + " — " + pretty_value +
                " (" + datetime.now().strftime("%H:%M") + ")")
        for u, _ in await list_family_members(e.family_id):
            try:
                await msg.bot.send_message(u.tg_id, text)
            except Exception:
                pass


@router.message(MeasureInput.waiting_value, F.text.startswith("/cancel"))
async def measure_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("Ввод отменён.", reply_markup=kb_elderly_menu())