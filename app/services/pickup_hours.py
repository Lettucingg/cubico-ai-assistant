"""Regular office pickup hours in Panama local time."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

PANAMA = ZoneInfo("America/Panama")
PICKUP_HOURS = "Lunes a viernes de 10:00 a 17:00; sábados de 10:00 a 13:00; domingos cerrado."


def pickup_window(now: datetime | None = None) -> tuple[bool, datetime]:
    """Return whether the office is open and the start of the available window."""
    local = now.astimezone(PANAMA) if now is not None else datetime.now(PANAMA)
    start = local.replace(hour=10, minute=0, second=0, microsecond=0)
    day = local.weekday()
    close = time(13 if day == 5 else 17)
    if day != 6 and time(10) <= local.time() < close:
        return True, start
    if day == 6 or local.time() >= close:
        start += timedelta(days=2 if day == 5 else 1)
    return False, start


def pickup_time_context() -> str:
    is_open, opening = pickup_window()
    day = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")[opening.weekday()]
    status = ("abierto según el horario habitual" if is_open else
              f"cerrado según el horario habitual; próxima apertura: {day} {opening:%d/%m/%Y} a las 10:00 a. m.")
    return f"Horario de retiro en Panamá: {PICKUP_HOURS} El local está {status}"
