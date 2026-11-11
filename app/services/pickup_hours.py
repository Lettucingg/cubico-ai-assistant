"""Regular office pickup hours in Panama local time."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

PANAMA = ZoneInfo("America/Panama")
PICKUP_HOURS = "Lunes a viernes de 10:00 a 17:00; sábados de 10:00 a 13:00; domingos cerrado."

# Confirmed office closures; public holidays do not imply the office always closes.
OFFICE_CLOSURES = {date(2026, 11, 10): "feriado"}


def pickup_window(now: datetime | None = None) -> tuple[bool, datetime]:
    """Return whether the office is open and the start of the available window."""
    local = now.astimezone(PANAMA) if now is not None else datetime.now(PANAMA)
    start = local.replace(hour=10, minute=0, second=0, microsecond=0)
    day = local.weekday()
    close = time(13 if day == 5 else 17)
    if day != 6 and local.date() not in OFFICE_CLOSURES and time(10) <= local.time() < close:
        return True, start
    if local.time() >= close:
        start += timedelta(days=1)
    while start.weekday() == 6 or start.date() in OFFICE_CLOSURES:
        start += timedelta(days=1)
    return False, start


def pickup_time_context() -> str:
    # Team-authored closures override the normal weekly schedule.
    from app.services.operational_context import service_block
    blocked = service_block("local") or service_block("retiros")
    if blocked:
        messages = " ".join(notice["mensaje"] for notice in blocked["avisos"])
        return ("RETIRO SUSPENDIDO según el aviso vigente del equipo: " + messages +
                " No afirmes que estamos abiertos ni prometas reapertura sin confirmación. "
                "Horario habitual de referencia, no vigente durante el cierre: " + PICKUP_HOURS)

    now = datetime.now(PANAMA)
    is_open, opening = pickup_window(now)
    reason = OFFICE_CLOSURES.get(now.date())
    day = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")[opening.weekday()]
    status = ("abierto según el horario habitual" if is_open else
              f"cerrado {'por ' + reason if reason else 'según el horario habitual'}; próxima apertura habitual: {day} {opening:%d/%m/%Y} a las 10:00 a. m.")
    return f"Horario de retiro en Panamá: {PICKUP_HOURS} El local está {status}"
