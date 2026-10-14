import base64
import logging
import os

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from app.config import settings
from app.db import (
    get_elderly, add_routine, get_routines, delete_all_routines,
    get_user_by_tg, can_edit_family_data,
)
from app.keyboards import kb_ai_preview, kb_family_menu
from app.services.prescription_ai import (
    generate_schedule_from_text,
    generate_schedule_from_image,
)
from app.services.pdf_text import extract_pdf_text
from app.services.formatting import format_when
from app.scheduler import schedule_absolute_routines

log = logging.getLogger(__name__)
router = Router()


class AISchedule(StatesGroup):
    waiting_text = State()


def _format_item(it):
    prefix = "🩺 " if it.get("measure_kind") else "• "
    when = format_when(it["mode"], it["offset_min"],
                       it.get("hour", 8), it.get("minute", 0))
    return prefix + it["title"] + " — " + when


async def _send_preview(msg: Message, state: FSMContext, eid: int, items: list):
    e = await get_elderly(eid)
    if not e:
        await state.clear()
        await msg.answer("Близкий не найден.")
        return

    await state.update_data(ai_items=items)

    existing = await get_routines(eid)
    text = "📋 Предлагаемый распорядок для " + e.name + ":\n\n"
    for it in items:
        text = text + _format_item(it) + "\n"
    text = text + (
        "\n⚠️ Это черновик, сгенерированный ИИ. "
        "Не является медицинской рекомендацией. Проверьте с врачом."
    )
    if existing:
        text = text + (
            "\n\n⚠️ У близкого уже есть " + str(len(existing)) + " задач. "
            "Выберите, что делать."
        )
    await msg.answer(text, reply_markup=kb_ai_preview(has_routines=bool(existing)))


@router.callback_query(F.data.startswith("tpl_ai:"))
async def ai_start(cb: CallbackQuery, state: FSMContext):
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
    if not await can_edit_family_data(e.family_id, user.id):
        await cb.answer("У вас нет прав на изменение.", show_alert=True)
        return
    await state.update_data(ai_eid=eid)
    await state.set_state(AISchedule.waiting_text)
    text = (
        "📄 Пришлите выписку врача.\n\n"
        "Подойдёт одно из:\n"
        "• 📸 Фотография выписки\n"
        "• 📎 PDF с текстом\n"
        "• 🎤 Голосовое (продиктуйте)\n"
        "• ✍️ Текст, скопированный из документа\n\n"
        "Я проанализирую и предложу распорядок.\n\n"
        "Важно: документ передаётся в GigaChat. Это черновик, "
        "не медицинская рекомендация — проверьте с врачом."
    )
    await cb.message.edit_text(text)
    await cb.answer()


@router.message(AISchedule.waiting_text, F.photo)
async def ai_process_photo(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    eid = data.get("ai_eid")
    e = await get_elderly(eid)
    if not e:
        await state.clear()
        await msg.answer("Близкий не найден.")
        return

    await msg.answer("📸 Анализирую фотографию. Это займёт 20–40 секунд…")

    path = None
    try:
        file = await bot.get_file(msg.photo[-1].file_id)
        os.makedirs("data/tmp", exist_ok=True)
        path = "data/tmp/ai_" + str(msg.from_user.id) + "_" + str(msg.message_id) + ".jpg"
        await bot.download_file(file.file_path, path)
    except Exception as ex:
        log.warning("photo download failed: %s", ex)
        await msg.answer("Не удалось скачать фото. Попробуйте ещё раз.")
        return

    try:
        with open(path, "rb") as f:
            image_bytes = f.read()
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
    except Exception as ex:
        log.warning("photo encode failed: %s", ex)
        await msg.answer("Не удалось обработать фото.")
        return
    finally:
        try:
            os.remove(path)
        except Exception:
            pass

    items = await generate_schedule_from_image(base64_image)
    if not items:
        await msg.answer(
            "Не удалось распознать выписку на фото. Попробуйте сфотографировать "
            "лучше — при хорошем освещении, без наклона, целиком.",
            reply_markup=kb_family_menu(),
        )
        await state.clear()
        return

    await _send_preview(msg, state, eid, items)


@router.message(AISchedule.waiting_text, F.document)
async def ai_process_document(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    eid = data.get("ai_eid")
    e = await get_elderly(eid)
    if not e:
        await state.clear()
        await msg.answer("Близкий не найден.")
        return

    doc = msg.document
    mime = (doc.mime_type or "").lower()
    name = (doc.file_name or "").lower()

    path = None
    try:
        file = await bot.get_file(doc.file_id)
        os.makedirs("data/tmp", exist_ok=True)
        if "pdf" in mime or name.endswith(".pdf"):
            path = "data/tmp/ai_doc_" + str(msg.from_user.id) + "_" + str(msg.message_id) + ".pdf"
        elif mime.startswith("image/"):
            path = "data/tmp/ai_doc_" + str(msg.from_user.id) + "_" + str(msg.message_id) + ".jpg"
        else:
            await msg.answer(
                "Пока я умею читать фото, PDF и текст. "
                "Пришлите документ в одном из этих форматов."
            )
            return
        await bot.download_file(file.file_path, path)
    except Exception as ex:
        log.warning("doc download failed: %s", ex)
        await msg.answer("Не удалось скачать файл.")
        return

    try:
        if path.endswith(".pdf"):
            await msg.answer("📄 Читаю PDF. Это займёт 20–40 секунд…")
            pdf_text = extract_pdf_text(path)
            if not pdf_text or len(pdf_text) < 20:
                await msg.answer(
                    "Не удалось извлечь текст из PDF. Возможно, это скан. "
                    "Сфотографируйте его или пришлите текстом."
                )
                await state.clear()
                return
            items = await generate_schedule_from_text(pdf_text)
        else:
            await msg.answer("📸 Анализирую изображение…")
            with open(path, "rb") as f:
                image_bytes = f.read()
            base64_image = base64.b64encode(image_bytes).decode("utf-8")
            items = await generate_schedule_from_image(base64_image)
    except Exception as ex:
        log.warning("doc process failed: %s", ex)
        items = None
    finally:
        try:
            os.remove(path)
        except Exception:
            pass

    if not items:
        await msg.answer(
            "Не удалось распознать документ. Попробуйте другой файл или текст.",
            reply_markup=kb_family_menu(),
        )
        await state.clear()
        return

    await _send_preview(msg, state, eid, items)


@router.message(AISchedule.waiting_text, F.voice)
async def ai_process_voice(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    eid = data.get("ai_eid")
    e = await get_elderly(eid)
    if not e:
        await state.clear()
        await msg.answer("Близкий не найден.")
        return

    await msg.answer("🎧 Слушаю голосовое…")

    path = None
    try:
        file = await bot.get_file(msg.voice.file_id)
        os.makedirs("data/tmp", exist_ok=True)
        path = "data/tmp/ai_voice_" + str(msg.from_user.id) + "_" + str(msg.message_id) + ".ogg"
        await bot.download_file(file.file_path, path)
    except Exception as ex:
        log.warning("voice download failed: %s", ex)
        await msg.answer("Не удалось скачать голосовое.")
        return

    try:
        import asyncio
        from app.voice import transcribe
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(
            None, transcribe, path, settings.WHISPER_MODEL
        )
    except Exception as ex:
        log.warning("voice transcribe failed: %s", ex)
        text = None
    finally:
        try:
            os.remove(path)
        except Exception:
            pass

    if not text or len(text) < 20:
        await msg.answer(
            "Не удалось распознать текст. Попробуйте записать ещё раз "
            "в тихом месте или напишите текстом."
        )
        return

    await msg.answer("🎤 Распознано: «" + text[:200] + "…»\n\n"
                     "Отправляю в GigaChat. Это займёт 20–40 секунд…")

    items = await generate_schedule_from_text(text)
    if not items:
        await msg.answer(
            "Не удалось собрать расписание. Попробуйте ещё раз или "
            "пришлите выписку текстом.",
            reply_markup=kb_family_menu(),
        )
        await state.clear()
        return

    await _send_preview(msg, state, eid, items)


@router.message(AISchedule.waiting_text, F.text, ~F.text.startswith("/"))
async def ai_process_text(msg: Message, state: FSMContext):
    data = await state.get_data()
    eid = data.get("ai_eid")
    e = await get_elderly(eid)
    if not e:
        await state.clear()
        await msg.answer("Близкий не найден.")
        return

    txt = (msg.text or "").strip()
    if len(txt) < 20:
        await msg.answer(
            "Слишком короткий текст. Пришлите полный текст выписки "
            "или фотографию."
        )
        return

    await msg.answer("🧠 Анализирую выписку. Это займёт 15–30 секунд…")

    items = await generate_schedule_from_text(txt)
    if not items:
        await msg.answer(
            "Не удалось распознать выписку. Попробуйте ещё раз или "
            "создайте задачи вручную.",
            reply_markup=kb_family_menu(),
        )
        await state.clear()
        return

    await _send_preview(msg, state, eid, items)


@router.callback_query(F.data == "ai_cancel")
async def ai_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Отменено. Задачи не добавлены.")
    await cb.answer()


@router.callback_query(F.data.startswith("ai_apply:"))
async def ai_apply(cb: CallbackQuery, state: FSMContext):
    mode = cb.data.split(":")[1]
    data = await state.get_data()
    eid = data.get("ai_eid")
    items = data.get("ai_items", [])
    e = await get_elderly(eid)
    if not e or not items:
        await cb.answer("Данные потеряны. Начните заново.", show_alert=True)
        await state.clear()
        return

    if mode == "replace":
        await delete_all_routines(eid)

    count = 0
    for it in items:
        await add_routine(
            eid, it["title"], mode="wake_offset",
            offset_min=it["offset_min"],
            measure_kind=it.get("measure_kind"),
        )
        count = count + 1

    await state.clear()
    await schedule_absolute_routines(cb.bot)

    action = "применено задач" if mode == "replace" else "добавлено задач"
    await cb.message.edit_text(
        "✅ Успешно " + action + ": " + str(count) + ".\n"
        "Откройте распорядок, чтобы проверить."
    )
    await cb.answer("Готово")