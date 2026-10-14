import asyncio
import logging

from openai import OpenAI

from app.config import settings

log = logging.getLogger(__name__)

_client_ultra = None
_client_default = None


def _get_client():
    """Один клиент — прокси разбирается, какую модель использовать."""
    global _client_ultra
    if _client_ultra is not None:
        return _client_ultra
    try:
        _client_ultra = OpenAI(
            base_url=settings.GPT2GIGA_URL,
            api_key=settings.GPT2GIGA_API_KEY,
            timeout=60,
        )
        return _client_ultra
    except Exception as e:
        log.warning("OpenAI proxy client init failed: %s", e)
        return None


def call_ultra(prompt):
    """Синхронный вызов GigaChat-3-Ultra через прокси."""
    client = _get_client()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model="GigaChat-3-Ultra",
            messages=[{"role": "user", "content": prompt}],
        )
        if response.choices:
            return (response.choices[0].message.content or "").strip()
        return None
    except Exception as e:
        log.warning("Ultra call failed: %s", e)
        return None


def call_default(prompt):
    """Синхронный вызов GigaChat-2-Pro через прокси (для отчётов)."""
    client = _get_client()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model="GigaChat-2-Pro",
            messages=[{"role": "user", "content": prompt}],
        )
        if response.choices:
            return (response.choices[0].message.content or "").strip()
        return None
    except Exception as e:
        log.warning("Default call failed: %s", e)
        return None


async def make_daily_summary(name, done, skipped, alarms, total, woke, wellbeing):
    woke_text = "да" if woke else "нет"
    prompt = (
        "Ты помощник сервиса заботы о близких. Сгенерируй короткий "
        "тёплый отчёт для родственника о прошедшем дне. Без медицинских "
        "советов, без диагнозов. 2-3 предложения, простой русский язык. "
        "Не используй Markdown.\n\n"
        "Данные:\n"
        "Имя: " + str(name) + "\n"
        "Пробуждение отмечено: " + woke_text + "\n"
        "Задачи выполнены: " + str(done) + " из " + str(total) + "\n"
        "Пропущено: " + str(skipped) + "\n"
        "Не подтверждено: " + str(alarms) + "\n"
        "Самочувствие: " + str(wellbeing) + "\n"
    )
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, call_default, prompt)
    except Exception as e:
        log.warning("make_daily_summary failed: %s", e)
        return None