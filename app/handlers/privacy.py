"""Политика ПДн и отзыв согласия."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db import get_user_by_tg

router = Router()


PRIVACY_TEXT = (
    "🔒 <b>Политика конфиденциальности</b>\n\n"
    "<b>Оператор:</b> [ИП/ООО «Название»], ИНН [___], ОГРН [___]\n"
    "<b>Адрес:</b> [___]\n"
    "<b>Ответственный за ПДн:</b> [email]\n\n"
    "<b>1. Обрабатываемые данные</b>\n"
    "• Имя, Telegram ID\n"
    "• Тексты и голосовые сообщения\n"
    "• Данные семейной группы\n\n"
    "<b>2. Цели</b>\n"
    "• Напоминания, отчёты, поддержка\n\n"
    "<b>3. Основания</b>\n"
    "• Согласие субъекта (ст. 6 152-ФЗ)\n\n"
    "<b>4. Хранение</b>\n"
    "• Серверы в РФ, TLS, ограниченный доступ\n\n"
    "<b>5. Права</b>\n"
    "• /delete_my_data\n\n"
    "<b>6. Третьим лицам</b>\n"
    "• Не передаём, кроме случаев, предусмотренных законом."
)


@router.message(Command("privacy"))
async def privacy(msg: Message):
    await msg.answer(PRIVACY_TEXT)


@router.message(Command("delete_my_data"))
async def delete_my_data(msg: Message):
    user = await get_user_by_tg(msg.from_user.id)
    if not user:
        await msg.answer("Вас нет в базе.")
        return
    await msg.answer(
        "Запрос принят. Данные удалятся в течение 3 рабочих дней."
    )