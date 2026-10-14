import asyncio
import json
import logging
import re

from openai import OpenAI

from app.config import settings

log = logging.getLogger(__name__)


PROMPT = (
    "Ты строгий медицинский парсер. Твоя задача — извлечь из врачебной "
    "выписки ТОЛЬКО то, что в ней прямо написано, и представить в виде "
    "расписания. Ты НЕ врач, ты НЕ добавляешь рекомендации от себя.\n\n"

    "ГЛАВНОЕ ПРАВИЛО:\n"
    "Добавляй в расписание ТОЛЬКО задачи, которые явно упомянуты "
    "в тексте выписки. Если чего-то нет в тексте — этого НЕ должно "
    "быть в расписании.\n\n"

    "ИСКЛЮЧЕНИЕ — три базовых приёма пищи:\n"
    "ВСЕГДА добавляй:\n"
    "  - Завтрак (offset_min = 30)\n"
    "  - Обед (offset_min = 300)\n"
    "  - Ужин (offset_min = 660)\n"
    "Даже если про них не сказано — они нужны для привязки лекарств.\n\n"

    "ЗАПРЕЩЕНО (важно!):\n"
    "- Добавлять замеры, которых нет в выписке. Если сказано только "
    "«контроль давления» — замеряем ТОЛЬКО давление. Сахар, пульс, "
    "вес — НЕ добавляем, даже если диагноз к ним располагает.\n"
    "- Добавлять лекарства, которых нет в выписке.\n"
    "- Добавлять витамины, добавки, БАДы, которые не упомянуты.\n"
    "- «Логически достраивать» расписание. Гипертония не повод мерить "
    "сахар. Диабет не повод мерить давление. Только то, что сказано.\n"
    "- Ставить больше 15 задач.\n"
    "- Ставить абсолютное время (08:00 и т.п.). Только offset_min.\n\n"

    "ПРИВЯЗКА К ПРОБУЖДЕНИЮ:\n"
    "Все задачи указываются через offset_min — количество минут после "
    "пробуждения. Не через время суток.\n"
    "Минимум offset_min = 15.\n\n"

    "ПРАВИЛА ВРЕМЕНИ:\n"
    "- Завтрак: offset_min = 30\n"
    "- Обед: offset_min = 300 (5 часов)\n"
    "- Ужин: offset_min = 660 (11 часов)\n"
    "- Лекарство «до еды» — на 15 минут раньше приёма пищи.\n"
    "- Лекарство «после еды» — на 15 минут позже.\n"
    "- «Натощак утром» -> offset_min = 15\n"
    "- «Утром» -> offset_min = 30 (привязать к завтраку)\n"
    "- «Вечером» -> offset_min = 660 (привязать к ужину)\n"
    "- «Перед сном» -> offset_min = 780\n\n"

    "КРАТНОСТЬ:\n"
    "- «1 раз в день утром» -> одна задача, offset_min = 30\n"
    "- «2 раза в день утром и вечером» -> ДВЕ задачи: 30 и 660\n"
    "- «3 раза в день» -> ТРИ задачи: 30, 300, 660\n\n"

    "ЗАМЕРЫ — ТОЛЬКО ЕСЛИ ЯВНО УКАЗАНЫ В ТЕКСТЕ:\n"
    "- «Контроль давления 2 раза в день утром и вечером» -> две задачи "
    "с measure_kind = pressure, offset 30 и 780\n"
    "- «Контроль сахара натощак» -> measure_kind = sugar, offset 15\n"
    "- «Контроль пульса» -> measure_kind = pulse, offset 30\n"
    "- «Контроль веса» -> measure_kind = weight, offset 30\n"
    "Если про замер не сказано — не добавляй.\n\n"

    "ПРОГУЛКИ И АКТИВНОСТЬ — ТОЛЬКО ЕСЛИ УПОМЯНУТЫ:\n"
    "- «Прогулка 30 минут ежедневно» -> одна задача offset_min = 120\n"
    "- «Зарядка» / «ЛФК» -> offset_min = 90\n\n"

    "ФОРМАТ НАЗВАНИЙ:\n"
    "- Лекарства: «Эналаприл 10 мг (1 таб.) - до еды»\n"
    "- Замеры: «Замер давления», «Замер сахара натощак»\n"
    "- Без лишних слов.\n\n"

    "ФОРМАТ ОТВЕТА — строго JSON, без Markdown, без пояснений:\n"
    "{\n"
    '  "items": [\n'
    '    {"title": "Завтрак", "offset_min": 30, "measure_kind": null},\n'
    '    {"title": "Эналаприл 10 мг (1 таб.) - до еды", "offset_min": 15, "measure_kind": null},\n'
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