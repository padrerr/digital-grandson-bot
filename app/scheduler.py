import logging
import os
from datetime import datetime, timedelta, date

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, and_

from app.config import settings
from app.db import (
    Session, User, Elderly, Event,
    get_elderly, get_routines, get_user, get_event, get_routine,
    create_event, set_event_status, list_family_members, clear_wake,
    events_between, is_quiet_hours, list_elderly_with_birthday,
    get_note, mark_note_sent, list_future_notes,
)
from app.keyboards import kb_routine_event, kb_wellbeing, kb_wake
from app.services.ai_summary import make_daily_summary
from app.services.notify import notify_task_alarm
from app.services.backup import make_backup
from app.services.monitor import heartbeat

log = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Asia/Krasnoyarsk")


async def _family_member_tgs(family_id):
    members = await list_family_members(family_id)
    return [u.tg_id for u, _ in members]


async def _notify_family(bot, e, text, urgent=False):
    if not urgent and is_quiet_hours(e, datetime.now()):
        return
    for tg in await _family_member_tgs(e.family_id):
        try:
            await bot.send_message(tg, text)
        except Exception:
            pass


async def send_wake_prompt(bot: Bot, elderly_id: int):
    e = await get_elderly(elderly_id)
    if not e or not e.active or not e.user_id:
        return
    if e.wake_date == date.today().isoformat():
        return
    u = await get_user(e.user_id)
    if not u:
        return
    try:
        await bot.send_message(
            u.tg_id,
            "☀️ Доброе утро! Нажмите кнопку, когда проснётесь — "
            "и я подстрою расписание под вас.",
            reply_markup=kb_wake(),
        )
    except Exception as ex:
        log.warning("wake prompt failed: %s", ex)


async def wake_timeout(bot: Bot, elderly_id: int):
    e = await get_elderly(elderly_id)
    if not e or e.wake_date == date.today().isoformat():
        return
    await _notify_family(bot, e, "⚠️ " + e.name + " ещё не отметил(а) пробуждение.")


async def send_routine(bot: Bot, routine_id: int):
    r = await get_routine(routine_id)
    if not r or not r.active:
        return
    e = await get_elderly(r.elderly_id)
    if not e or not e.active or not e.user_id:
        return
    u = await get_user(e.user_id)
    if not u:
        return
    ev = await create_event(r.elderly_id, "routine", routine_id=r.id)
    is_measure = bool(r.measure_kind)
    try:
        if is_measure:
            from app.services import measurements as M
            unit = M.unit(r.measure_kind)
            example = M.example(r.measure_kind)
            body = (
                "Пора: " + r.title + "\n\n"
                "Введите значение " + M.label(r.measure_kind) +
                (" в " + unit if unit else "") + ".\n"
                "Например: " + example
            )
            await bot.send_message(
                u.tg_id, body,
                reply_markup=kb_routine_event(ev.id, is_measure=True),
            )
        else:
            await bot.send_message(
                u.tg_id,
                "🔔 Пора: " + r.title + "\nПодтвердите, пожалуйста:",
                reply_markup=kb_routine_event(ev.id, is_measure=False),
            )
    except Exception as ex:
        log.warning("send_routine failed: %s", ex)
        return
    scheduler.add_job(
        routine_reminder, "date",
        run_date=datetime.now() + timedelta(minutes=settings.REMINDER_AFTER_MIN),
        args=[bot, ev.id], id="rm_" + str(ev.id), replace_existing=True,
    )


async def routine_reminder(bot: Bot, event_id: int):
    ev = await get_event(event_id)
    if not ev or ev.status != "pending":
        return
    e = await get_elderly(ev.elderly_id)
    if not e:
        return
    r = await get_routine(ev.routine_id) if ev.routine_id else None
    title = r.title if r else "задача"
    if e.user_id:
        u = await get_user(e.user_id)
        if u:
            try:
                await bot.send_message(
                    u.tg_id,
                    "⏰ Напоминаю: " + title + "\nНажмите кнопку:",
                    reply_markup=kb_routine_event(event_id),
                )
            except Exception:
                pass
    await notify_task_alarm(bot, e, title)
    await set_event_status(event_id, "alarm")


async def send_wellbeing(bot: Bot, elderly_id: int):
    e = await get_elderly(elderly_id)
    if not e or not e.user_id:
        return
    u = await get_user(e.user_id)
    if not u:
        return
    ev = await create_event(elderly_id, "wellbeing")
    try:
        await bot.send_message(
            u.tg_id,
            "Как вы себя чувствуете? Выберите вариант.",
            reply_markup=kb_wellbeing(),
        )
    except Exception as ex:
        log.warning("send_wellbeing failed: %s", ex)
        return
    scheduler.add_job(
        wellbeing_reminder, "date",
        run_date=datetime.now() + timedelta(minutes=settings.WELLBEING_REMINDER_MIN),
        args=[bot, ev.id], id="wb_rm_" + str(ev.id), replace_existing=True,
    )


async def wellbeing_reminder(bot: Bot, event_id: int):
    ev = await get_event(event_id)
    if not ev or ev.status != "pending":
        return
    e = await get_elderly(ev.elderly_id)
    if not e or not e.user_id:
        return
    u = await get_user(e.user_id)
    if not u:
        return
    try:
        await bot.send_message(
            u.tg_id,
            "Как вы себя чувствуете? Пожалуйста, ответьте — близкие ждут.",
            reply_markup=kb_wellbeing(),
        )
    except Exception:
        pass
    delta = settings.WELLBEING_ALERT_MIN - settings.WELLBEING_REMINDER_MIN
    if delta < 0:
        delta = 0
    scheduler.add_job(
        wellbeing_alarm, "date",
        run_date=datetime.now() + timedelta(minutes=delta),
        args=[bot, event_id], id="wb_al_" + str(event_id), replace_existing=True,
    )


async def wellbeing_alarm(bot: Bot, event_id: int):
    ev = await get_event(event_id)
    if not ev or ev.status != "pending":
        return
    e = await get_elderly(ev.elderly_id)
    if not e:
        return
    await set_event_status(event_id, "alarm")
    await _notify_family(
        bot, e, "⚠️ " + e.name + " не ответил(а) на вопрос о самочувствии."
    )


WELLBEING_LABELS = {
    "good": "хорошо",
    "ok": "так себе",
    "bad": "плохо",
    "help": "нужна помощь",
    "critical": "тревога",
}


async def evening_report(bot: Bot):
    async with Session() as s:
        elderlies = (await s.execute(
            select(Elderly).where(Elderly.active == True)
        )).scalars().all()
    for e in elderlies:
        start = datetime.combine(date.today(), datetime.min.time())
        end = start + timedelta(days=1)
        events = await events_between(e.id, start, end)
        routine_events = [x for x in events if x.kind == "routine"]
        done = sum(1 for x in routine_events if x.status == "done")
        skipped = sum(1 for x in routine_events if x.status == "skipped")
        alarms = sum(1 for x in routine_events if x.status == "alarm")
        total = len(routine_events)
        woke = (e.wake_date == date.today().isoformat())
        wb = [x for x in events if x.kind == "wellbeing"]
        last_wb = wb[-1].status if wb else "—"
        wb_label = WELLBEING_LABELS.get(last_wb, last_wb)
        ai_text = await make_daily_summary(
            name=e.name, done=done, skipped=skipped, alarms=alarms,
            total=total, woke=woke, wellbeing=wb_label,
        )
        if ai_text:
            text = "📊 Вечерний отчёт — " + e.name + "\n\n" + ai_text
        else:
            text = (
                "📊 Отчёт за день — " + e.name + "\n"
                "Пробуждение: " + ("✅" if woke else "—") + "\n"
                "Задачи: ✅ " + str(done) + ", ⏭ " + str(skipped)
                + ", 🚨 " + str(alarms) + " из " + str(total) + "\n"
                "Самочувствие: " + wb_label
            )
        await _notify_family(bot, e, text)


async def schedule_day_for_elderly(bot: Bot, elderly_id: int):
    e = await get_elderly(elderly_id)
    if not e or not e.wake_at:
        return
    base = e.wake_at
    routines = await get_routines(elderly_id)
    for r in routines:
        if r.mode == "wake_offset":
            when = base + timedelta(minutes=r.offset_min)
            if when < datetime.now():
                continue
            scheduler.add_job(
                send_routine, "date",
                run_date=when,
                args=[bot, r.id],
                id="day_" + str(elderly_id) + "_" + str(r.id),
                replace_existing=True,
            )
    scheduler.add_job(
        send_wellbeing, "date",
        run_date=base + timedelta(hours=settings.WELLBEING_AFTER_HOURS),
        args=[bot, elderly_id],
        id="wb_" + str(elderly_id), replace_existing=True,
    )


async def schedule_absolute_routines(bot: Bot):
    async with Session() as s:
        elderlies = (await s.execute(
            select(Elderly).where(Elderly.active == True)
        )).scalars().all()
    for e in elderlies:
        routines = await get_routines(e.id)
        for r in routines:
            if r.mode == "absolute":
                scheduler.add_job(
                    send_routine, "cron",
                    hour=r.hour, minute=r.minute,
                    args=[bot, r.id],
                    id="abs_" + str(e.id) + "_" + str(r.id),
                    replace_existing=True,
                )


async def birthday_check(bot: Bot):
    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    for target_date, label in ((today, "сегодня"), (tomorrow, "завтра")):
        mm_dd = target_date.strftime("%m-%d")
        elderlies = await list_elderly_with_birthday(mm_dd)
        for e in elderlies:
            for u, _ in await list_family_members(e.family_id):
                text = ("🎂 Напоминание: у " + e.name + " " + label
                        + " день рождения!")
                try:
                    await bot.send_message(u.tg_id, text)
                except Exception:
                    pass


async def send_note_reminder(bot: Bot, note_id: int):
    n = await get_note(note_id)
    if not n or n.status != "pending":
        return
    e = await get_elderly(n.elderly_id)
    if not e or not e.user_id:
        return
    u = await get_user(e.user_id)
    if not u:
        return
    try:
        await bot.send_message(
            u.tg_id,
            "📝 Напоминание: " + n.text + "\n\n"
            "Когда пройдёт — нажмите кнопку ниже.",
        )
        scheduler.add_job(
            ask_note_feedback, "date",
            run_date=datetime.now() + timedelta(hours=1),
            args=[bot, note_id],
            id="note_ask_" + str(note_id),
            replace_existing=True,
        )
    except Exception as ex:
        log.warning("send_note_reminder failed: %s", ex)
    await mark_note_sent(note_id)


async def ask_note_feedback(bot: Bot, note_id: int):
    n = await get_note(note_id)
    if not n or n.status == "done":
        return
    e = await get_elderly(n.elderly_id)
    if not e or not e.user_id:
        return
    u = await get_user(e.user_id)
    if not u:
        return
    try:
        from app.keyboards import kb_note_feedback
        await bot.send_message(
            u.tg_id,
            "📝 Как прошло: " + n.text + "?",
            reply_markup=kb_note_feedback(n.id),
        )
    except Exception as ex:
        log.warning("ask_note_feedback failed: %s", ex)


async def schedule_note(bot: Bot, note_id: int):
    n = await get_note(note_id)
    if not n or n.status != "pending":
        return
    when = n.remind_at
    if when <= datetime.now():
        when = datetime.now() + timedelta(seconds=5)
    scheduler.add_job(
        send_note_reminder, "date",
        run_date=when,
        args=[bot, note_id],
        id="note_" + str(note_id),
        replace_existing=True,
    )


async def reschedule_all_notes(bot: Bot):
    notes = await list_future_notes()
    for n in notes:
        await schedule_note(bot, n.id)


async def scheduled_backup(bot: Bot):
    result = make_backup()
    if result:
        log.info("Backup done: %s", result)
    else:
        log.warning("Backup failed")


async def cleanup_tmp_files():
    """Удаляет файлы из data/tmp и data/voice старше 1 часа."""
    now = datetime.now().timestamp()
    for folder in ("data/tmp", "data/voice"):
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                continue
            try:
                mtime = os.path.getmtime(path)
                if now - mtime > 3600:
                    os.remove(path)
                    log.info("Removed old tmp file: %s", path)
            except Exception as ex:
                log.warning("Cleanup failed for %s: %s", path, ex)


async def scheduled_heartbeat():
    heartbeat()


async def _register_daily_jobs(bot: Bot, e: Elderly):
    scheduler.add_job(
        send_wake_prompt, "cron",
        hour=7, minute=0,
        args=[bot, e.id],
        id="wake_" + str(e.id), replace_existing=True,
    )
    scheduler.add_job(
        wake_timeout, "cron",
        hour=e.checkin_hour, minute=0,
        args=[bot, e.id],
        id="wake_to_" + str(e.id), replace_existing=True,
    )


async def _has_event_today(elderly_id, routine_id, kind="routine"):
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = today_start + timedelta(days=1)
    async with Session() as s:
        q = select(Event).where(
            and_(Event.elderly_id == elderly_id,
                 Event.kind == kind,
                 Event.created_at >= today_start,
                 Event.created_at < today_end)
        )
        if routine_id is not None:
            q = q.where(Event.routine_id == routine_id)
        r = await s.execute(q)
        return r.scalars().first() is not None


async def restore_today_tasks(bot: Bot):
    today = date.today().isoformat()
    async with Session() as s:
        elderlies = (await s.execute(
            select(Elderly).where(
                Elderly.active == True,
                Elderly.wake_date == today,
                Elderly.wake_at.isnot(None)
            )
        )).scalars().all()

    now = datetime.now()
    for e in elderlies:
        base = e.wake_at
        routines = await get_routines(e.id)
        for r in routines:
            if r.mode == "wake_offset":
                when = base + timedelta(minutes=r.offset_min)
                if when <= now:
                    continue
                if await _has_event_today(e.id, r.id, "routine"):
                    continue
                scheduler.add_job(
                    send_routine, "date",
                    run_date=when,
                    args=[bot, r.id],
                    id="day_" + str(e.id) + "_" + str(r.id),
                    replace_existing=True,
                )
                log.info("Restored routine %s for elderly %s at %s",
                         r.id, e.id, when)

        wb_time = base + timedelta(hours=settings.WELLBEING_AFTER_HOURS)
        if wb_time > now and not await _has_event_today(e.id, None, "wellbeing"):
            scheduler.add_job(
                send_wellbeing, "date",
                run_date=wb_time,
                args=[bot, e.id],
                id="wb_" + str(e.id), replace_existing=True,
            )
            log.info("Restored wellbeing for elderly %s at %s", e.id, wb_time)


async def restore_pending_events(bot: Bot):
    now = datetime.now()
    async with Session() as s:
        cutoff = now - timedelta(hours=24)
        r = await s.execute(
            select(Event).where(
                and_(Event.status == "pending", Event.created_at >= cutoff)
            )
        )
        events = list(r.scalars().all())

    for ev in events:
        e = await get_elderly(ev.elderly_id)
        if not e or not e.user_id:
            continue

        if ev.kind == "routine":
            elapsed = (now - ev.created_at).total_seconds() / 60.0
            if elapsed < settings.REMINDER_AFTER_MIN:
                run_at = ev.created_at + timedelta(minutes=settings.REMINDER_AFTER_MIN)
                scheduler.add_job(
                    routine_reminder, "date",
                    run_date=run_at, args=[bot, ev.id],
                    id="rm_" + str(ev.id), replace_existing=True,
                )
                log.info("Restored routine_reminder for event %s", ev.id)
            elif elapsed < settings.FAMILY_ALERT_AFTER_MIN:
                scheduler.add_job(
                    routine_reminder, "date",
                    run_date=now + timedelta(seconds=5), args=[bot, ev.id],
                    id="rm_" + str(ev.id), replace_existing=True,
                )
                log.info("Immediate routine_reminder for event %s", ev.id)
            else:
                r_obj = await get_routine(ev.routine_id) if ev.routine_id else None
                title = r_obj.title if r_obj else "задача"
                await notify_task_alarm(bot, e, title)
                await set_event_status(ev.id, "alarm")
                log.info("Immediate alarm for event %s", ev.id)

        elif ev.kind == "wellbeing":
            elapsed = (now - ev.created_at).total_seconds() / 60.0
            if elapsed < settings.WELLBEING_REMINDER_MIN:
                run_at = ev.created_at + timedelta(minutes=settings.WELLBEING_REMINDER_MIN)
                scheduler.add_job(
                    wellbeing_reminder, "date",
                    run_date=run_at, args=[bot, ev.id],
                    id="wb_rm_" + str(ev.id), replace_existing=True,
                )
                log.info("Restored wellbeing_reminder for event %s", ev.id)
            elif elapsed < settings.WELLBEING_ALERT_MIN:
                scheduler.add_job(
                    wellbeing_reminder, "date",
                    run_date=now + timedelta(seconds=5), args=[bot, ev.id],
                    id="wb_rm_" + str(ev.id), replace_existing=True,
                )
                log.info("Immediate wellbeing_reminder for event %s", ev.id)
            else:
                await wellbeing_alarm(bot, ev.id)
                log.info("Immediate wellbeing_alarm for event %s", ev.id)


async def daily_rollover(bot: Bot):
    async with Session() as s:
        elderlies = (await s.execute(
            select(Elderly).where(Elderly.active == True)
        )).scalars().all()
    for e in elderlies:
        await clear_wake(e.id)
        await _register_daily_jobs(bot, e)
    log.info("Daily rollover done for %s elderly", len(elderlies))


async def bootstrap(bot: Bot):
    async with Session() as s:
        elderlies = (await s.execute(
            select(Elderly).where(Elderly.active == True)
        )).scalars().all()

    for e in elderlies:
        await _register_daily_jobs(bot, e)

    now = datetime.now()
    for e in elderlies:
        if not e.user_id:
            continue
        if e.wake_date == date.today().isoformat():
            continue
        if now.hour >= e.checkin_hour or now.hour < 7:
            continue
        try:
            await send_wake_prompt(bot, e.id)
        except Exception as ex:
            log.warning("bootstrap wake prompt failed: %s", ex)

    await schedule_absolute_routines(bot)
    await restore_today_tasks(bot)
    await restore_pending_events(bot)
    await reschedule_all_notes(bot)

    scheduler.add_job(
        evening_report, "cron",
        hour=settings.EVENING_REPORT_HOUR,
        minute=settings.EVENING_REPORT_MINUTE,
        args=[bot], id="evening_report", replace_existing=True,
    )
    scheduler.add_job(
        daily_rollover, "cron",
        hour=0, minute=5, args=[bot], id="rollover", replace_existing=True,
    )
    scheduler.add_job(
        schedule_absolute_routines, "cron",
        hour=0, minute=10, args=[bot], id="abs_reschedule", replace_existing=True,
    )
    scheduler.add_job(
        birthday_check, "cron",
        hour=settings.BIRTHDAY_HOUR,
        minute=settings.BIRTHDAY_MINUTE,
        args=[bot], id="birthday_check", replace_existing=True,
    )
    scheduler.add_job(
        scheduled_backup, "cron",
        hour=3, minute=0,
        args=[bot], id="backup", replace_existing=True,
    )
    scheduler.add_job(
        cleanup_tmp_files, "cron",
        hour=4, minute=0,
        id="cleanup_tmp", replace_existing=True,
    )
    scheduler.add_job(
        scheduled_heartbeat, "interval",
        minutes=5, id="heartbeat", replace_existing=True,
    )
    heartbeat()