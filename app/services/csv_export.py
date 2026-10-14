"""
Экспорт истории по близкому в CSV: события, самочувствие, замеры.
"""
import csv
import os
import tempfile

from app.db import (
    get_elderly, get_routines, all_events, all_wellbeing_logs,
    all_measurements,
)
from app.services import measurements as M

KIND_LABELS = {
    "routine": "Задача",
    "wellbeing": "Самочувствие",
    "wake": "Пробуждение",
}

STATUS_LABELS = {
    "done": "выполнено",
    "skipped": "пропущено",
    "alarm": "не подтвердил",
    "pending": "ожидает",
    "good": "хорошо",
    "ok": "так себе",
    "bad": "плохо",
    "help": "нужна помощь",
    "critical": "критично",
}


async def export_history(elderly_id: int):
    e = await get_elderly(elderly_id)
    if not e:
        return None

    events = await all_events(elderly_id)
    logs = await all_wellbeing_logs(elderly_id)
    measures = await all_measurements(elderly_id)
    routines = {r.id: r for r in await get_routines(elderly_id)}

    rows = []

    for ev in events:
        title = ""
        if ev.routine_id and ev.routine_id in routines:
            title = routines[ev.routine_id].title
        rows.append((
            ev.created_at.strftime("%Y-%m-%d"),
            ev.created_at.strftime("%H:%M:%S"),
            KIND_LABELS.get(ev.kind, ev.kind),
            title or ev.note or "",
            STATUS_LABELS.get(ev.status, ev.status),
        ))

    for lg in logs:
        rows.append((
            lg.created_at.strftime("%Y-%m-%d"),
            lg.created_at.strftime("%H:%M:%S"),
            "Сообщение",
            lg.text,
            lg.category,
        ))

    for m in measures:
        rows.append((
            m.created_at.strftime("%Y-%m-%d"),
            m.created_at.strftime("%H:%M:%S"),
            "Замер: " + M.label(m.kind),
            M.pretty(m.kind, m.value),
            m.note or "",
        ))

    rows.sort(key=lambda x: (x[0], x[1]))

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False,
        encoding="utf-8-sig", newline="",
    )
    writer = csv.writer(tmp, delimiter=";")
    writer.writerow(["Дата", "Время", "Тип", "Содержание", "Статус"])
    for r in rows:
        writer.writerow(r)
    tmp.close()

    filename = e.name.replace(" ", "_") + "_history.csv"
    return tmp.name, filename, len(rows)


def cleanup(path: str):
    try:
        os.remove(path)
    except Exception:
        pass