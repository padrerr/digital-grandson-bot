import logging
from app.config import settings

log = logging.getLogger(__name__)

ALARM_WORDS = [
    "упал", "упала", "задыха", "не могу дышать", "боль в груди",
    "болит сердце", "кровь", "не встаю", "плохо мне", "вызовите",
    "скорая", "инсульт", "инфаркт", "потерял сознание", "теряю сознание",
]

_giga = None


def _client():
    global _giga
    if _giga is not None:
        return _giga
    if not settings.GIGACHAT_CREDENTIALS:
        return None
    try:
        from gigachat import GigaChat
        _giga = GigaChat(credentials=settings.GIGACHAT_CREDENTIALS, verify_ssl_certs=False)
        return _giga
    except Exception as e:
        log.warning("GigaChat init failed: %s", e)
        return None


def rule_based_alarm(text: str) -> str | None:
    """Возвращает категорию тревоги или None."""
    low = text.lower()
    for w in ALARM_WORDS:
        if w in low:
            return "critical"
    for w in ["болит", "голова", "тошнит", "слабость", "температура", "плохо"]:
        if w in low:
            return "warning"
    return None


def ai_analyze(text: str) -> str | None:
    """Просит GigaChat оценить текст. Возвращает 'critical'|'warning'|'ok'|None."""
    g = _client()
    if g is None:
        return None
    try:
        prompt = (
            "Ты ассистент по уходу за пожилыми. Оцени сообщение пожилого человека. "
            "Ответь ОДНИМ словом: critical (угроза жизни), warning (жалоба на здоровье), "
            "ok (нейтрально/бытовое). Не давай медицинских советов.\n\n"
            f"Сообщение: {text}"
        )
        resp = g.chat(prompt)
        ans = resp.choices[0].message.content.strip().lower()
        if "critical" in ans:
            return "critical"
        if "warning" in ans:
            return "warning"
        if "ok" in ans:
            return "ok"
        return None
    except Exception as e:
        log.warning("GigaChat failed: %s", e)
        return None


def analyze(text: str) -> str | None:
    """Правила важнее ИИ. Возвращает итоговую категорию."""
    r = rule_based_alarm(text)
    if r == "critical":
        return "critical"
    a = ai_analyze(text)
    # ИИ может только повышать уровень, но не понижать ниже warning
    if a == "critical":
        return "critical"
    if r == "warning" or a == "warning":
        return "warning"
    return a or "ok"