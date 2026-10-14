def format_offset(minutes):
    """Переводит минуты в человеческий вид: 15 мин, 1 час, 5 часов."""
    try:
        m = int(minutes)
    except (ValueError, TypeError):
        m = 0
    if m <= 0:
        return "15 мин"
    if m < 60:
        return str(m) + " мин"
    hours = m // 60
    mins = m % 60
    if mins == 0:
        if hours == 1:
            return "1 час"
        if 2 <= hours <= 4:
            return str(hours) + " часа"
        return str(hours) + " часов"
    if hours == 1:
        return "1 ч " + str(mins) + " мин"
    return str(hours) + " ч " + str(mins) + " мин"


def format_when(mode, offset_min, hour=8, minute=0):
    """Возвращает человеческую строку времени."""
    if mode == "wake_offset":
        return "через " + format_offset(offset_min) + " после пробуждения"
    try:
        h = int(hour)
        m = int(minute)
    except (ValueError, TypeError):
        h, m = 8, 0
    return f"в {h:02d}:{m:02d}"