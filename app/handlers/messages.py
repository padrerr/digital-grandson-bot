import logging
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.db import (
    get_user_by_tg, get_elderly_by_user, get_user_family,
    list_family_members, list_family_elderly, get_elderly, get_user,
    log_wellbeing, is_quiet_hours,
)
from app.services.wellbeing import classify, is_alert
from app.handlers.actions import apply_wellbeing_level
from app.keyboards import kb_recipient_pick

log = logging.getLogger(__name__)
router = Router()


VOICE_DISABLED_TEXT = (
    "🎤 Голосовые сообщения временно недоступны.\n\n"
    "Пожалуйста, напишите текстом или используйте кнопки внизу."
)


class IsElderly(BaseFilter):
    async def __call__(self, event) -> bool:
        if not hasattr(event, "from_user") or event.from_user is None:
            return False
        user = await get_user_by_tg(event.from_user.id)
        if not user:
            return False
        e = await get_elderly_by_user(user.id)
        return bool(e)


class IsFamily(BaseFilter):
    async def __call__(self, event) -> bool:
        if not hasattr(event, "from_user") or event.from_user is None:
            return False
        user = await get_user_by_tg(event.from_user.id)
        if not user:
            return False
        uf = await get_user_family(user.id)
        return bool(uf)


class MessageToElderly(StatesGroup):
    waiting = State()


class MessageToRelative(StatesGroup):
    waiting = State()


SYSTEM_BUTTONS = {
    "☀️ Я проснулся",
    "😊 Как я себя чувствую",
    "🩺 Сообщить о проблеме",
    "📋 Мои задачи",
    "❓ Как пользоваться ботом?",
    "📊 Отчёты",
    "📨 Мои заявки",
    "🛠 Написать в техподдержку",
    "✉️ Отправить сообщение близкому",
    "✉️ Отправить сообщение родственнику",
    "👨‍👩‍👧 Моя семья",
    "⚙️ Аккаунт",
}


HINT = (
    "Можно отправить:\n"
    "📝 текст\n"
    "🎥 видеокружок\n"
    "📷 изображение\n\n"
    "Чтобы отменить — отправьте /cancel"
)


# ============================================================
# РОДСТВЕННИК → БЛИЗКИЙ
# ============================================================

@router.message(F.text == "✉️ Отправить сообщение близкому", IsFamily())
async def to_elderly_start(msg: Message, state: FSMContext):
    user = await get_user_by_tg(msg.from_user.id)
    uf = await get_user_family(user.id)
    f, _ = uf
    elderly = await list_family_elderly(f.id)
    if not elderly:
        await msg.answer("В семье нет близких.")
        return
    if len(elderly) == 1:
        await state.update_data(msg_eid=elderly[0].id)
        await state.set_state(MessageToElderly.waiting)
        await msg.answer(
            "Отправьте сообщение для " + elderly[0].name + ".\n\n" + HINT
        )
        return
    await state.set_state(MessageToElderly.waiting)
    await msg.answer(
        "Кому отправить?",
        reply_markup=kb_recipient_pick(elderly, prefix="msg_to_e"),
    )


@router.callback_query(F.data.startswith("msg_to_e:"))
async def to_elderly_pick(cb: CallbackQuery, state: FSMContext):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    e = await get_elderly(eid)
    if not e:
        await cb.answer("Не найден", show_alert=True)
        return
    await state.update_data(msg_eid=eid)
    await state.set_state(MessageToElderly.waiting)
    await cb.message.edit_text(
        "Отправьте сообщение для " + e.name + ".\n\n" + HINT
    )
    await cb.answer()


async def _elderly_chat_id(e):
    if not e or not e.user_id:
        return None
    user = await get_user(e.user_id)
    if not user:
        return None
    return user.tg_id


async def _deliver_to_elderly(bot: Bot, e, msg: Message, kind: str,
                              sender_name: str):
    chat_id = await _elderly_chat_id(e)
    if not chat_id:
        await msg.answer(
            "Близкий ещё не подключён к боту. "
            "Отправьте ему ссылку-приглашение из панели близкого."
        )
        return False
    prefix = "✉️ Сообщение от " + sender_name + ":"
    try:
        if kind == "text":
            await bot.send_message(chat_id, prefix + "\n\n" + (msg.text or ""))
        elif kind == "photo":
            cap = prefix
            if msg.caption:
                cap = cap + "\n\n" + msg.caption
            await bot.send_photo(chat_id, msg.photo[-1].file_id, caption=cap)
        elif kind == "video_note":
            await bot.send_message(chat_id, prefix)
            await bot.send_video_note(chat_id, msg.video_note.file_id)
        return True
    except Exception as ex:
        log.warning("deliver_to_elderly failed: %s", ex)
        await msg.answer("Не удалось отправить сообщение. Попробуйте позже.")
        return False


async def _process_to_elderly(msg: Message, state: FSMContext, kind: str):
    data = await state.get_data()
    eid = data.get("msg_eid")
    e = await get_elderly(eid) if eid else None
    if not e:
        await state.clear()
        await msg.answer("Сессия потеряна. Начните заново.")
        return
    user = await get_user_by_tg(msg.from_user.id)
    sender = (user.name if user and user.name else "родственника")
    ok = await _deliver_to_elderly(msg.bot, e, msg, kind, sender)
    if ok:
        await msg.answer("✅ Отправлено")
    await state.clear()


@router.message(MessageToElderly.waiting, F.text, ~F.text.startswith("/"))
async def to_elderly_text(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if not txt:
        await msg.answer("Пожалуйста, напишите текстом.")
        return
    await _process_to_elderly(msg, state, "text")


@router.message(MessageToElderly.waiting, F.photo)
async def to_elderly_photo(msg: Message, state: FSMContext):
    await _process_to_elderly(msg, state, "photo")


@router.message(MessageToElderly.waiting, F.video_note)
async def to_elderly_video_note(msg: Message, state: FSMContext):
    await _process_to_elderly(msg, state, "video_note")


@router.message(MessageToElderly.waiting, F.voice)
async def to_elderly_voice(msg: Message, state: FSMContext):
    await msg.answer(VOICE_DISABLED_TEXT)


# ============================================================
# БЛИЗКИЙ → РОДСТВЕННИКИ
# ============================================================

@router.message(F.text == "✉️ Отправить сообщение родственнику", IsElderly())
async def to_relative_start(msg: Message, state: FSMContext):
    user = await get_user_by_tg(msg.from_user.id)
    e = await get_elderly_by_user(user.id)
    members = await list_family_members(e.family_id)
    if not members:
        await msg.answer("В семье нет родственников.")
        return
    await state.set_state(MessageToRelative.waiting)
    await state.update_data(msg_from_elderly_id=e.id)
    await msg.answer(
        "Кому отправить?",
        reply_markup=kb_recipient_pick(
            [u for u, _ in members],
            prefix="msg_to_u",
            all_label="👥 Всем сразу",
            all_callback="msg_to_all",
        ),
    )


@router.callback_query(F.data == "msg_to_all")
async def to_relative_all(cb: CallbackQuery, state: FSMContext):
    await state.update_data(msg_target="all")
    await state.set_state(MessageToRelative.waiting)
    await cb.message.edit_text(
        "Отправьте сообщение всем родственникам.\n\n" + HINT
    )
    await cb.answer()


@router.callback_query(F.data.startswith("msg_to_u:"))
async def to_relative_pick(cb: CallbackQuery, state: FSMContext):
    try:
        uid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    u = await get_user(uid)
    if not u:
        await cb.answer("Не найден", show_alert=True)
        return
    await state.update_data(msg_target=str(uid))
    await state.set_state(MessageToRelative.waiting)
    await cb.message.edit_text(
        "Отправьте сообщение для " + u.name + ".\n\n" + HINT
    )
    await cb.answer()


async def _deliver_to_relatives(bot: Bot, e, msg: Message, kind: str,
                                targets):
    members = await list_family_members(e.family_id)
    if targets == "all":
        tgs = [u.tg_id for u, _ in members]
    else:
        uid = int(targets)
        tgs = []
        for u, _ in members:
            if u.id == uid:
                tgs.append(u.tg_id)
                break
    if not tgs:
        await msg.answer("Получатель не найден.")
        return False
    prefix = "✉️ Сообщение от " + e.name + ":"
    delivered = 0
    for tg in tgs:
        try:
            if kind == "text":
                await bot.send_message(tg, prefix + "\n\n" + (msg.text or ""))
            elif kind == "photo":
                cap = prefix
                if msg.caption:
                    cap = cap + "\n\n" + msg.caption
                await bot.send_photo(tg, msg.photo[-1].file_id, caption=cap)
            elif kind == "video_note":
                await bot.send_message(tg, prefix)
                await bot.send_video_note(tg, msg.video_note.file_id)
            delivered = delivered + 1
        except Exception as ex:
            log.warning("deliver to %s failed: %s", tg, ex)
    if delivered == 0:
        await msg.answer(
            "Не удалось доставить сообщение ни одному получателю.\n\n"
            "Возможно, получатель ещё не открывал бота — попросите его "
            "нажать /start в Telegram."
        )
    return delivered > 0


async def _process_to_relative(msg: Message, state: FSMContext, kind: str):
    data = await state.get_data()
    eid = data.get("msg_from_elderly_id")
    target = data.get("msg_target")
    e = await get_elderly(eid) if eid else None
    if not e or not target:
        await state.clear()
        await msg.answer("Сессия потеряна. Начните заново.")
        return
    ok = await _deliver_to_relatives(msg.bot, e, msg, kind, target)
    if ok:
        await msg.answer("✅ Отправлено")
    else:
        await msg.answer("Не удалось отправить.")
    await state.clear()


@router.message(MessageToRelative.waiting, F.text, ~F.text.startswith("/"))
async def to_relative_text(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if not txt:
        await msg.answer("Пожалуйста, напишите текстом.")
        return
    await _process_to_relative(msg, state, "text")


@router.message(MessageToRelative.waiting, F.photo)
async def to_relative_photo(msg: Message, state: FSMContext):
    await _process_to_relative(msg, state, "photo")


@router.message(MessageToRelative.waiting, F.video_note)
async def to_relative_video_note(msg: Message, state: FSMContext):
    await _process_to_relative(msg, state, "video_note")


@router.message(MessageToRelative.waiting, F.voice)
async def to_relative_voice(msg: Message, state: FSMContext):
    await msg.answer(VOICE_DISABLED_TEXT)


# ============================================================
# ОТМЕНА
# ============================================================

@router.callback_query(F.data == "pick_cancel")
async def pick_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Отменено.")
    await cb.answer()


@router.message(MessageToElderly.waiting, F.text.startswith("/cancel"))
async def cancel_to_elderly(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("Отменено.")


@router.message(MessageToRelative.waiting, F.text.startswith("/cancel"))
async def cancel_to_relative(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("Отменено.")


# ============================================================
# ФОТО ОТ БЛИЗКОГО
# ============================================================

@router.message(F.photo, IsElderly())
async def photo_from_elderly(msg: Message, bot: Bot, state: FSMContext):
    if await state.get_state():
        return
    user = await get_user_by_tg(msg.from_user.id)
    e = await get_elderly_by_user(user.id)
    caption = "📷 " + e.name + " прислал(а) фото"
    if msg.caption:
        caption = caption + "\n" + msg.caption
    for u, _ in await list_family_members(e.family_id):
        try:
            await bot.send_photo(u.tg_id, msg.photo[-1].file_id, caption=caption)
        except Exception as ex:
            log.warning("photo forward failed: %s", ex)
    await msg.answer("Спасибо! Передал близким 📷")


# ============================================================
# ВИДЕОКРУЖОК ОТ БЛИЗКОГО
# ============================================================

@router.message(F.video_note, IsElderly())
async def video_note_from_elderly(msg: Message, bot: Bot, state: FSMContext):
    if await state.get_state():
        return
    user = await get_user_by_tg(msg.from_user.id)
    e = await get_elderly_by_user(user.id)
    for u, _ in await list_family_members(e.family_id):
        try:
            await bot.send_video_note(u.tg_id, msg.video_note.file_id)
            await bot.send_message(u.tg_id, "🎥 " + e.name + " прислал(а) видеокружок")
        except Exception as ex:
            log.warning("video_note forward failed: %s", ex)
    await msg.answer("Передал близким 🎥")


# ============================================================
# ГОЛОСОВОЕ ОТ БЛИЗКОГО — ВРЕМЕННО ОТКЛЮЧЕНО
# ============================================================

@router.message(F.voice, IsElderly())
async def voice_from_elderly(msg: Message, state: FSMContext):
    if await state.get_state():
        return
    await msg.answer(VOICE_DISABLED_TEXT)


# ============================================================
# СВОБОДНЫЙ ТЕКСТ ОТ БЛИЗКОГО
# ============================================================

@router.message(F.text & ~F.text.startswith("/"), IsElderly())
async def free_text(msg: Message, state: FSMContext):
    if await state.get_state():
        return
    user = await get_user_by_tg(msg.from_user.id)
    e = await get_elderly_by_user(user.id)
    txt = (msg.text or "").strip()
    if not txt or txt in SYSTEM_BUTTONS:
        return

    level = classify(txt)
    if is_alert(level):
        async def reply(text):
            await msg.answer(text)
        await apply_wellbeing_level(msg.bot, e, level, reply,
                                    source="text", log_text=txt)
    elif level in ("good", "ok"):
        await log_wellbeing(e.id, txt, level, source="text")
        await msg.answer("Спасибо, что написали! Рад за вас.")
    else:
        await log_wellbeing(e.id, txt, "unknown", source="text")
        if not is_quiet_hours(e, datetime.now()):
            for u, _ in await list_family_members(e.family_id):
                try:
                    await msg.bot.send_message(u.tg_id, "📝 " + e.name + ": " + txt)
                except Exception:
                    pass
        await msg.answer("Передал близким.")