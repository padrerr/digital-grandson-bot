import logging
from datetime import datetime

from aiogram import Bot

from app.db import (
    Elderly, list_family_members, is_quiet_hours, is_user_muted,
)
from app.keyboards import kb_alert_actions

log = logging.getLogger(__name__)


TASK_LABELS = {
    "done": "✅ выполнил(а)",
    "skipped": "⏭ пропустил(а)",
    "alarm": "⚠️ не подтвердил(а)",
}

WELLBEING_LABELS = {
    "bad": "плохо себя чувствует",
    "help": "нужна помощь",
    "critical": "🚨 ТРЕВОГА: возможна угроза жизни",
}


async def _send_to_user(bot: Bot, tg_id: int, text: str,
                        elderly_id=None, kind=None, summary="",
                        force: bool = False):
    """Отправляет одному пользователю с учётом mute."""
    if not force:
        try:
            from app.db import get_user_by_tg
            u = await get_user_by_tg(tg_id)
            if u and await is_user_muted(u.id):
                log.info("user %s is muted, skip", tg_id)
                return False
        except Exception as ex:
            log.warning("mute check failed: %s", ex)

    try:
        if elderly_id and kind:
            await bot.send_message(
                tg_id, text,
                reply_markup=kb_alert_actions(elderly_id, kind, summary),
            )
        else:
            await bot.send_message(tg_id, text)
        return True
    except Exception as ex:
        log.warning("send_to_user failed for %s: %s", tg_id, ex)
        return False


async def notify_family(bot: Bot, elderly: Elderly, text: str,
                        urgent: bool = False, elderly_id=None,
                        kind=None, summary="") -> None:
    if not urgent and is_quiet_hours(elderly, datetime.now()):
        return
    for user, _ in await list_family_members(elderly.family_id):
        await _send_to_user(bot, user.tg_id, text,
                            elderly_id=elderly_id, kind=kind,
                            summary=summary, force=urgent)


async def notify_task_action(bot: Bot, elderly_id: int,
                             title: str, action: str) -> None:
    from app.db import get_elderly
    e = await get_elderly(elderly_id)
    if not e:
        return
    label = TASK_LABELS.get(action, action)
    text = e.name + " " + label + ": «" + title + "»"
    if not is_quiet_hours(e, datetime.now()):
        for user, _ in await list_family_members(e.family_id):
            try:
                await bot.send_message(user.tg_id, text)
            except Exception:
                pass


async def notify_wellbeing(bot: Bot, elderly: Elderly, level: str) -> None:
    label = WELLBEING_LABELS.get(level, level)
    text = "⚠️ " + elderly.name + ": " + label
    kind = "wellbeing_" + level
    summary = elderly.name + ": " + label
    await notify_family(bot, elderly, text,
                        urgent=(level == "critical"),
                        elderly_id=elderly.id, kind=kind, summary=summary)


async def notify_task_alarm(bot: Bot, elderly, title: str) -> None:
    text = "⚠️ " + elderly.name + " не подтвердил(а): «" + title + "»."
    summary = elderly.name + ": не подтвердил(а) «" + title + "»"
    await notify_family(bot, elderly, text,
                        elderly_id=elderly.id,
                        kind="task_alarm", summary=summary)


async def notify_problem(bot: Bot, elderly, summary: str,
                         urgent: bool) -> None:
    kind = "problem_critical" if urgent else "problem"
    await notify_family(bot, elderly, summary,
                        urgent=urgent,
                        elderly_id=elderly.id, kind=kind,
                        summary=summary)


async def notify_note_feedback(bot: Bot, elderly, text: str) -> None:
    """Простое уведомление об ответе на заметку."""
    if is_quiet_hours(elderly, datetime.now()):
        return
    for user, _ in await list_family_members(elderly.family_id):
        try:
            await bot.send_message(user.tg_id, text)
        except Exception:
            pass