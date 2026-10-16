import asyncio
import json
import logging
import re

from openai import OpenAI

from app.config import settings

log = logging.getLogger(__name__)


PROMPT = (
    "Ты медицинский ассистент. Проанализируй врачебную выписку и составь "
    "расписание ДНЕВНЫХ задач для пожилого человека. Ты НЕ врач, ты "
    "только извлекаешь задачи из текста.\n\n"

    "ЗАДАЧА:\n"
    "Найти в тексте всё, что можно превратить в ежедневные задачи: "
    "приём лекарств, замеры здоровья. Всё остальное (обследования, "
    "анализы, диеты, школы здоровья, консультации врачей) ИГНОРИРУЙ — "
    "это не задачи расписания.\n\n"

    "ЧТО БРАТЬ:\n"
    "1. Лекарства с ежедневным приёмом (постоянные или курсом):\n"
    "   - Название, доза (например «Эналаприл 10 мг» или «1 табл»).\n"
    "   - Время: «утром» → 30 мин после пробуждения, "
    "«вечером» → 660 мин, «днём» → 300 мин, «натощак» → 15 мин, "
    "«перед сном» → 780 мин.\n"
    "   - Привязка к еде: «до еды» — за 15 мин до приёма пищи; "
    "«после еды» — через 15 мин; «во время еды» — вместе.\n"
    "   - Если сказано «2 раза в день» — ДВЕ задачи: утром и вечером.\n"
    "   - Если «3 раза в день» — ТРИ задачи: утро, день, вечер.\n\n"
    "2. Замеры здоровья (только если упомянуты):\n"
    "   - «Контроль АД» / «артериального давления» → measure_kind = pressure.\n"
    "   - «Контроль сахара» / «глюкозы» → measure_kind = sugar.\n"
    "   - «Контроль пульса» / «ЧСС» → measure_kind = pulse.\n"
    "   - «Контроль веса» → measure_kind = weight.\n"
    "   - Время: утром → 30, вечером → 780.\n\n"

    "ЧТО ИГНОРИРОВАТЬ (очень важно):\n"
    "- Обследования: МРТ, КТ, УЗИ, ЭКГ, рентген, ДС БЦА, липидограмма.\n"
    "- Анализы: ОАК, ОАМ, биохимия, ТТГ, калий, креатинин, мочевина, РАК.\n"
    "- Консультации врачей: нефролог, кардиолог, эндокринолог, психиатр.\n"
    "- Школы здоровья, посещения, приёмы.\n"
    "- Диеты, ограничения соли, DASH, калории.\n"
    "- Рекомендации по физической активности (аэробные нагрузки, прогулки).\n"
    "- Целевые показатели («АД 120-129», «холестерин < 4,0»).\n"
    "- Титрование по неделям (Миртазапин: 1/4 → 1/2 → 1 табл) — "
    "БЕРИ ТОЛЬКО КОНЕЧНУЮ ДОЗУ (с 4 недели — 1 таблетка).\n"
    "- Общие фразы без конкретики.\n\n"

    "ПРИМЕРЫ:\n"
    "«Индапамид 1,5 мг по 1 табл утром» → задача «Индапамид 1,5 мг», "
    "offset_min = 30.\n"
    "«Бисопролол 10 мг по 1 табл утром натощак» → задача "
    "«Бисопролол 10 мг (натощак)», offset_min = 15.\n"
    "«Аторвастатин 20 мг вечером после еды» → задача "
    "«Аторвастатин 20 мг (после еды)», offset_min = 675.\n"
    "«Холина альфосцерат 400 мг по 1 табл утром в течение 1 месяца» "
    "→ задача «Холина альфосцерат 400 мг», offset_min = 30.\n"
    "«Ежедневный контроль АД и пульса» → ДВЕ задачи: "
    "«Замер давления» (pressure) и «Замер пульса» (pulse), "
    "offset_min = 30.\n\n"

    "ПРАВИЛА ВРЕМЕНИ (offset_min — минуты после пробуждения):\n"
    "- натощак → 15\n"
    "- утром → 30 (к завтраку)\n"
    "- до завтрака → 15\n"
    "- после завтрака → 45\n"
    "- днём → 300 (к обеду)\n"
    "- до обеда → 285\n"
    "- после обеда → 315\n"
    "- вечером → 660 (к ужину)\n"
    "- до ужина → 645\n"
    "- после ужина → 675\n"
    "- перед сном → 780\n"
    "Минимум = 15. Максимум = 1440.\n\n"

    "ВСЕГДА ДОБАВЛЯЙ базовые приёмы пищи, даже если их нет в выписке:\n"
    "- Завтрак: offset_min = 30\n"
    "- Обед: offset_min = 300\n"
    "- Ужин: offset_min = 660\n\n"

    "МАКСИМУМ 15 задач. Если получается больше — оставь только лекарства "
    "и замеры, убери приёмы пищи.\n\n"

    "ФОРМАТ ОТВЕТА — строго JSON без Markdown и пояснений:\n"
    "{\n"
    '  "items": [\n'
    '    {"title": "Завтрак", "offset_min": 30, "measure_kind": null},\n'
    '    {"title": "Индапамид 1,5 мг", "offset_min": 30, "measure_kind": null},\n'
    '    {"title": "Замер давления", "offset_min": 30, "measure_kind": "pressure"}\n'
    "  ]\n"
    "}\n\n"

    "Текст выписки:\n"
)

IMAGE_PROMPT = PROMPT.replace(
    "Текст выписки:",
    "Распознай текст на изображении и действуй по тем же правилам. "
    "Изображение прилагается."
)


_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    try:
        _client = OpenAI(
            base_url=settings.GPT2GIGA_URL,
            api_key=settings.GPT2GIGA_API_KEY,
            timeout=90,
        )
        return _client
    except Exception as e:
        log.warning("OpenAI proxy client init failed: %s", e)
        return None


def _extract_json(text):
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    raw = text[start:end + 1]
    try:
        return json.loads(raw)
    except Exception as e:
        log.warning("JSON parse failed: %s", e)
        return None


def _normalize_offset(it):
    offset = None
    if "offset_min" in it:
        try:
            offset = int(it.get("offset_min"))
        except (ValueError, TypeError):
            offset = None
    if offset is None:
        try:
            h = int(it.get("hour", 8))
            m = int(it.get("minute", 0))
        except (ValueError, TypeError):
            h, m = 8, 0
        abs_min = h * 60 + m
        base = 8 * 60
        offset = abs_min - base
        if offset < 0:
            offset = 0
    if offset < 15:
        offset = 15
    if offset > 1440:
        offset = 1440
    return offset


def _validate_item(it):
    if not isinstance(it, dict):
        return None
    title = str(it.get("title", "")).strip()
    if not title:
        return None
    offset = _normalize_offset(it)
    kind = it.get("measure_kind")
    if kind not in (None, "pressure", "sugar", "weight", "pulse"):
        kind = None
    return {
        "title": title[:100],
        "mode": "wake_offset",
        "offset_min": offset,
        "hour": 8,
        "minute": 0,
        "measure_kind": kind,
    }


def _dedup(items):
    seen = set()
    out = []
    for it in items:
        key = (it["title"].lower(), it["offset_min"])
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _ensure_base_meals(items):
    needed = [
        ("Завтрак", 30),
        ("Обед", 300),
        ("Ужин", 660),
    ]
    titles = {it["title"].lower() for it in items}
    for name, offset in needed:
        if name.lower() not in titles:
            items.append({
                "title": name,
                "mode": "wake_offset",
                "offset_min": offset,
                "hour": 8,
                "minute": 0,
                "measure_kind": None,
            })
    return items


def _postfilter_by_source(items, source_text):
    if not source_text:
        return items
    t = source_text.lower()

    keywords = {
        "pressure": ["давлен", "гипертон"],
        "sugar": ["сахар", "глюкоз", "диабет"],
        "weight": ["вес", "масс"],
        "pulse": ["пульс", "чсс"],
    }

    filtered = []
    for it in items:
        kind = it.get("measure_kind")
        if kind and kind in keywords:
            kws = keywords[kind]
            if not any(kw in t for kw in kws):
                log.info("Filtered hallucination: %s (kind=%s)", it["title"], kind)
                continue
        filtered.append(it)

    if "прогул" not in t and "ходьб" not in t and "лфк" not in t:
        filtered = [
            it for it in filtered
            if "прогул" not in it["title"].lower()
            and "ходьб" not in it["title"].lower()
        ]

    return filtered


def _postprocess_items(data, source_text=None):
    if not data or "items" not in data:
        return None
    items = data["items"]
    if not isinstance(items, list):
        return None
    result = []
    for it in items:
        clean = _validate_item(it)
        if clean:
            result.append(clean)
        if len(result) >= 25:
            break
    result = _dedup(result)
    result = _ensure_base_meals(result)
    if source_text:
        result = _postfilter_by_source(result, source_text)
    result.sort(key=lambda x: x["offset_min"])
    return result if result else None


def _call_ultra_sync(prompt):
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
        log.warning("Ultra text call failed: %s", e)
        return None


def _call_ultra_vision_sync(messages):
    client = _get_client()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model="GigaChat-3-Ultra",
            messages=messages,
        )
        if response.choices:
            return (response.choices[0].message.content or "").strip()
        return None
    except Exception as e:
        log.warning("Ultra vision call failed: %s", e)
        return None


async def generate_schedule_from_text(text: str):
    full_prompt = PROMPT + text
    try:
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, _call_ultra_sync, full_prompt)
        if not raw:
            log.warning("Ultra returned no text")
            return None
        data = _extract_json(raw)
        if not data:
            log.warning("AI returned no JSON. Raw: %s", raw[:500])
            return None
        return _postprocess_items(data, source_text=text)
    except Exception as e:
        log.warning("generate_schedule_from_text failed: %s", e)
        return None


async def generate_schedule_from_image(base64_image: str):
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": IMAGE_PROMPT},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/jpeg;base64," + base64_image
                    },
                },
            ],
        }
    ]
    try:
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(
            None, _call_ultra_vision_sync, messages
        )
        if not raw:
            log.warning("Ultra vision returned no text")
            return None
        data = _extract_json(raw)
        if not data:
            log.warning("AI vision returned no JSON. Raw: %s", raw[:500])
            return None
        return _postprocess_items(data, source_text=None)
    except Exception as e:
        log.warning("generate_schedule_from_image failed: %s", e)
        return None