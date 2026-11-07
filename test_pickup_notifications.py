import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import notificaciones as notices
from app.services.pickup_hours import PANAMA, pickup_window


def test_pickup_hours_use_panama_and_exclude_the_closing_minute():
    assert pickup_window(datetime(2026, 11, 7, 17, 59, tzinfo=timezone.utc))[0]
    for hour, minute in [(18, 0), (18, 52)]:
        opened, next_open = pickup_window(datetime(2026, 11, 7, hour, minute, tzinfo=timezone.utc))
        assert not opened
        assert next_open == datetime(2026, 11, 9, 10, tzinfo=PANAMA)
    assert pickup_window(datetime(2026, 11, 8, 12, tzinfo=PANAMA))[1] == next_open
    assert pickup_window(next_open)[0]
    assert not pickup_window(datetime(2026, 11, 9, 17, tzinfo=PANAMA))[0]


def test_saturday_notice_waits_until_monday_and_is_not_sent_twice(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'queue.db'}")
    notices.AvisoRetiroProgramado.__table__.create(engine)
    monkeypatch.setattr(notices, 'SessionSesiones', sessionmaker(bind=engine))
    monkeypatch.setattr(notices, '_ip_autorizada', lambda _: True)
    monkeypatch.setattr(notices.settings, 'CUBICO_NOTIFY_KEY', 'test')
    current = datetime(2026, 11, 7, 13, 52, tzinfo=PANAMA)
    monkeypatch.setattr(notices, 'pickup_window', lambda: pickup_window(current))

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return current.astimezone(tz)

    monkeypatch.setattr(notices, 'datetime', Clock)
    send = AsyncMock(return_value={'ok': True})
    monkeypatch.setattr(notices, '_enviar_carga_llegada', send)
    body = dict(telefono='50700000000', nombre='Prueba', codigo='TEST', tracking='TEST1',
                factura='TEST2', monto='78.40', paquetes='9')
    request = SimpleNamespace(headers={}, client=None, json=AsyncMock(return_value=body))

    async def scenario():
        first = await notices.notificar_carga_llegada(request, 'test')
        assert first['programado'] and not first['enviado']
        assert first['programado_para'] == '2026-11-09T15:00:00+00:00'
        assert first == await notices.notificar_carga_llegada(request, 'test')
        await notices.procesar_avisos_retiro()
        send.assert_not_awaited()

        nonlocal current
        current = datetime(2026, 11, 9, 10, 0, tzinfo=PANAMA)
        await asyncio.gather(notices.procesar_avisos_retiro(), notices.procesar_avisos_retiro())
        send.assert_awaited_once_with(notices.CargaLlegadaBody(**body))
        assert (await notices.notificar_carga_llegada(request, 'test'))['enviado']

    asyncio.run(scenario())
