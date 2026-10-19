import logging
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, FSInputFile

from app.db import (
    get_user_by_tg, get_user_family, list_family_elderly,
    get_elderly, events_between, list_user_help_requests,
    create_help_request, list_admins, list_wellbeing_logs,
)
from app.keyboards import kb_help_confirm, kb_reports_menu, kb_report_elderly
from app.services.csv_export import export_history, cleanup

log = logging.getLogger(__name__)
router = Router()


class HelpRequest(StatesGroup):
    enter_text = State()


# ============================================================
# ЗАЯВКА О ПОМОЩИ
# ============================================================

@router.message(F.text == "🛠 Написать в техподдержку")
async def help_start(msg: Message, state: FSMContext):
    await state.set_state(HelpRequest.enter_text)
    await msg.answer(
        "Опишите, пожалуйста, ваш вопрос или проблему одним сообщением. "
        "Мы постараемся помочь как можно скорее."
    )


@router.message(HelpRequest.enter_text, F.text, ~F.text.startswith("/"))
async def help_text(msg: Message, state: FSMContext):
    txt = (msg.text or "").strip()
    if not txt:
        await msg.answer("Пожалуйста, напишите текстом.")
        return
    await state.update_data(help_text=txt)
    await msg.answer(
        "Проверьте вашу заявку:\n\n" + txt + "\n\nОтправляем?",
        reply_markup=kb_help_confirm(),
    )


@router.callback_query(F.data == "help:cancel")
async def help_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Заявка отменена.")
    await cb.answer()


@router.callback_query(F.data == "help:send")
async def help_send(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    txt = data.get("help_text", "").strip()
    if not txt:
        await cb.answer("Текст потерян", show_alert=True)
        await state.clear()
        return

    user = await get_user_by_tg(cb.from_user.id)
    if not user:
        await cb.answer("Пользователь не найден", show_alert=True)
        await state.clear()
        return

    uf = await get_user_family(user.id)
    fam_id = uf[0].id if uf else None
    hr = await create_help_request(user.id, fam_id, txt)

    await state.clear()
    await cb.message.edit_text(
        "✅ Обращение #" + str(hr.id) + " отправлено. "
        "Ответ придёт в чат и будет храниться в «📨 История обращений»."
    )
    await cb.answer("Отправлено")

    uname = user.name or "id" + str(user.tg_id)
    fam_name = uf[0].name if uf else "—"
    admin_text = (
        "📨 Новая заявка #" + str(hr.id) + "\n"
        "От: " + uname + " (@" + (cb.from_user.username or "—") + ")\n"
        "Семья: " + fam_name + "\n\n" + txt
    )
    for admin in await list_admins():
        try:
            await cb.bot.send_message(admin.tg_id, admin_text)
        except Exception as ex:
            log.warning("admin notify failed: %s", ex)


# ============================================================
# МОИ ЗАЯВКИ
# ============================================================

@router.message(F.text == "📨 История обращений")
async def my_help_requests(msg: Message):
    user = await get_user_by_tg(msg.from_user.id)
    if not user:
        return
    reqs = await list_user_help_requests(user.id)
    if not reqs:
        await msg.answer(
            "📨 История обращений\n\n"
            "У вас пока нет обращений.\n\n"
            "Чтобы создать — нажмите «🛠 Написать в техподдержку»."
        )
        return

    lines = ["📨 Ваши заявки"]
    for hr in reqs[:20]:
        d = hr.created_at.strftime("%d.%m %H:%M")
        if hr.status == "new":
            lines.append(
                "\n#" + str(hr.id) + " от " + d + " — ожидает ответа\n" + hr.request_text
            )
        else:
            lines.append(
                "\n#" + str(hr.id) + " от " + d + " — отвечено\n"
                "Вы: " + hr.request_text + "\n"
                "Ответ: " + (hr.reply_text or "—")
            )
    await msg.answer("\n".join(lines))


# ============================================================
# ОТЧЁТЫ — меню
# ============================================================

@router.message(F.text == "📊 Отчёты")
async def reports_root(msg: Message):
    user = await get_user_by_tg(msg.from_user.id)
    if not user:
        return
    uf = await get_user_family(user.id)
    if not uf:
        return
    f, _ = uf
    elderly = await list_family_elderly(f.id)
    if not elderly:
        await msg.answer(
            "📊 Отчёты\n\n"
            "В вашей семье пока нет близких.\n"
            "Добавьте близкого в «👨‍👩‍👧 Моя семья» → «❤️ Близкие»."
        )
        return
    text = (
        "📊 Отчёты\n\n"
        "Выберите близкого, чтобы посмотреть отчёт за 7 дней, "
        "или скачать полную историю в CSV."
    )
    await msg.answer(text, reply_markup=kb_reports_menu(elderly))


@router.callback_query(F.data == "rep_root")
async def reports_back(cb: CallbackQuery):
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
    text = (
        "📊 Отчёты\n\n"
        "Выберите близкого, чтобы посмотреть отчёт за 7 дней, "
        "или скачать полную историю в CSV."
    )
    await cb.message.edit_text(text, reply_markup=kb_reports_menu(elderly))
    await cb.answer()


@router.callback_query(F.data.startswith("rep_view:"))
async def report_view(cb: CallbackQuery):
    try:
        eid = int(cb.data.split(":")[1])
    except (ValueError, IndexError):
        await cb.answer()
        return
    e = await get_elderly(eid)
    if not e:
        await cb.answer("Не найден", show_alert=True)
        return

    end = datetime.now()
    start = end - timedelta(days=7)
    events = await events_between(e.id, start, end)
    routine_events = [x for x in events if x.kind == "routine"]
    done = sum(1 for x in routine_events if x.status == "done")
    skipped = sum(1 for x in routine_events if x.status == "skipped")
    alarms = sum(1 for x in routine_events if x.status == "alarm")

    logs = await list_wellbeing_logs(e.id, limit=500)
    logs_week = [lg for lg in logs if lg.created_at >= start]

    if not routine_events and not logs_week:
        text = (
            "📊 " + e.name + "\n\n"
            "Пока нет данных за последние 7 дней."
        )
    else:
        text = (
            "📊 Отчёт за 7 дней — " + e.name + "\n\n"
            "Задачи: ✅ " + str(done) + ", ⏭ " + str(skipped)
            + ", 🚨 " + str(alarms) + "\n"
            "Всего задач: " + str(len(routine_events)) + "\n"
            "Сообщений о самочувствии: " + str(len(logs_week))
        )
    await cb.message.edit_text(text, reply_markup=kb_report_elderly(eid))
    await cb.answer()


@router.callback_query(F.data.startswith("rep_csv:"))
async def report_csv(cb: CallbackQuery):
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
    caption = "📥 История — " + e.name + "\nЗаписей: " + str(count)
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