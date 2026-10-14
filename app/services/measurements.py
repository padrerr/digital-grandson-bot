"""
Замеры здоровья: валидация, форматирование, метки.
"""
import re

# Виды замеров
KINDS = {
    "pressure": {
        "label": "давление",
        "full_label": "артериальное давление",
        "unit": "мм рт. ст.",
        "example": "120/80",
        "pattern": r"^\d{2,3}\s*[/\\]\s*\d{2,3}$",
        "normalize": lambda x: re.sub(r"\s+", "", x.replace("\\", "/")),
    },
    "sugar": {
        "label": "сахар",
        "full_label": "сахар в крови",
        "unit": "ммоль/л",
        "example": "5.6",
        "pattern": r"^\d{1,2}([.,]\d{1,2})?$",
        "normalize": lambda x: x.replace(",", "."),
    },
    "weight": {
        "label": "вес",
        "full_label": "вес",
        "unit": "кг",
        "example": "75.5",
        "pattern": r"^\d{2,3}([.,]\d{1,2})?$",
        "normalize": lambda x: x.replace(",", "."),
    },
    "pulse": {
        "label": "пульс",
        "full_label": "пульс",
        "unit": "уд/мин",
        "example": "72",
        "pattern": r"^\d{2,3}$",
        "normalize": lambda x: x,
    },
}


def validate(kind: str, text: str) -> str | None:
    """
    Проверяет и нормализует введённое значение.
    Возвращает нормализованное значение или None, если формат неверный.
    """
    if kind not in KINDS or not text:
        return None
    text = text.strip()
    info = KINDS[kind]
    if not re.match(info["pattern"], text):
        return None
    return info["normalize"](text)


def label(kind: str) -> str:
    return KINDS.get(kind, {}).get("label", kind)


def full_label(kind: str) -> str:
    return KINDS.get(kind, {}).get("full_label", kind)


def unit(kind: str) -> str:
    return KINDS.get(kind, {}).get("unit", "")


def example(kind: str) -> str:
    return KINDS.get(kind, {}).get("example", "")


def pretty(kind: str, value: str) -> str:
    """Красивая строка для отображения: '120/80 мм рт. ст.'"""
    u = unit(kind)
    return value + (" " + u if u else "")