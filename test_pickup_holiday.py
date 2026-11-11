from datetime import datetime
from unittest.mock import AsyncMock
from app.services import pickup_hours as hours, operational_context as notices


def test_confirmed_holiday_is_closed_and_skipped():
    stamp = lambda day, hour: datetime(2026, 11, day, hour, tzinfo=hours.PANAMA)
    assert hours.pickup_window(stamp(10, 8)) == (False, stamp(11, 10))
    assert hours.pickup_window(stamp(10, 11)) == (False, stamp(11, 10))
    assert hours.pickup_window(stamp(9, 17)) == (False, stamp(11, 10))
    assert hours.pickup_window(stamp(11, 10))[0]


def test_manual_closure_overrides_open_context(monkeypatch):
    monkeypatch.setattr(notices, 'service_block', lambda service: {
        'avisos': [{'mensaje': 'Cerrado por feriado'}]} if service == 'local' else None)
    result = hours.pickup_time_context()
    assert 'RETIRO SUSPENDIDO' in result and 'Cerrado por feriado' in result
    assert 'El local está abierto' not in result


def test_worker_does_not_send_when_panel_suspends_pickup(monkeypatch):
    import asyncio
    from app.api import notificaciones as api
    monkeypatch.setattr(api, 'pickup_window', lambda: (True, None))
    monkeypatch.setattr(api, 'service_block', lambda service: {'suspension_operativa': True})
    send = AsyncMock()
    monkeypatch.setattr(api, '_enviar_carga_llegada', send)
    asyncio.run(api.procesar_avisos_retiro())
    send.assert_not_awaited()
