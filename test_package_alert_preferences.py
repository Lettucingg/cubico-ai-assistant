import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session_store import TrackingVigilado, PreferenciasAvisos, EnvioPanelUnico
from app.services import package_alerts as packages, notification_preferences as prefs, panel_send_once as send_once, push_notifications as push


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'alerts.db'))
    for table in (TrackingVigilado, PreferenciasAvisos, EnvioPanelUnico):
        table.__table__.create(engine)
    session = sessionmaker(bind=engine)
    for module in (packages, prefs, send_once):
        monkeypatch.setattr(module, 'SessionSesiones', session)
    yield
    engine.dispose()


NOW = datetime(2026, 10, 6, 14)
def result(days=6, **overrides):
    return {'encontrado': True, 'ubicacion': 'Miami', 'registros_proveedor': [
        {'fecha_ingreso_proveedor': (NOW - timedelta(days=days)).isoformat() + 'Z'}], **overrides}


def test_six_days_boundary_and_confirmed_panama():
    assert packages.observar('T', '507', result(5.99), NOW) == []
    alerts = packages.observar('T', '507', result(), NOW)
    assert len(alerts) == 1 and alerts[0]['kind'] == 'demora_miami'
    assert '6 días' in alerts[0]['descripcion']
    assert packages.observar('T', '507', {'error': 'timeout'}, NOW) == []
    assert len(packages.listar_alertas(NOW)) == 1
    assert packages.observar('T', '507', {'encontrado': False}, NOW) == []
    assert len(packages.listar_alertas(NOW)) == 1
    packages.observar('T', '507', result(ubicacion='Panamá'), NOW)
    assert packages.listar_alertas(NOW) == []


@pytest.mark.parametrize('date', [None, 'bad', '2026-09-01T14:00:00', '2026-10-07T14:00:00Z'])
def test_missing_naive_invalid_future_dates_do_not_alert(date):
    data = result()
    data['registros_proveedor'].append({'fecha_ingreso_proveedor': date})
    assert packages.observar('T', '507', data, NOW) == []


def test_malid_has_explicit_title_and_resolves():
    alerts = packages.observar('T', '507', result(1, identificacion_incorrecta=True), NOW)
    assert alerts[0]['kind'] == 'malid'
    assert alerts[0]['titulo'] == 'Paquete mal identificado · T'
    packages.observar('T', '507', result(1, identificacion_incorrecta=False), NOW)
    assert packages.listar_alertas(NOW) == []


def test_push_only_once_and_archived_suppressed(monkeypatch):
    from app.services import alert_archive
    monkeypatch.setattr(alert_archive, 'listar_archivadas', lambda: [])
    notify = AsyncMock()
    monkeypatch.setattr(push, 'notificar_alerta_push', notify)
    async def run():
        alerts = packages.observar('T', '507', result(), NOW)
        await asyncio.gather(packages.notificar_nuevas(alerts), packages.notificar_nuevas(alerts))
        assert notify.await_count == 1
        assert packages.observar('T', '507', result(), NOW) == []
        hidden = packages.observar('OTHER', '507', result(), NOW)
        monkeypatch.setattr(alert_archive, 'listar_archivadas', lambda: [{'clave': hidden[0]['clave']}])
        await packages.notificar_nuevas(hidden)
        assert notify.await_count == 1
    asyncio.run(run())


def test_preferences_persist_and_filter_real_delivery_loop(monkeypatch):
    assert prefs.obtener('alexander') == 'ambos'
    prefs.guardar('alexander', 'alertas'); prefs.guardar('luis', 'chats')
    assert prefs.obtener('alexander') == 'alertas'
    assert prefs.obtener('teresa') == 'ambos'
    monkeypatch.setattr(push, 'push_configurado', lambda: True)
    monkeypatch.setattr(push, 'listar_suscripciones_push', lambda: [
        {'usuario': name, 'endpoint': name, 'keys': {}} for name in ['alexander', 'luis', 'teresa']])
    delivered = []
    monkeypatch.setattr(push, 'webpush', lambda **kw: delivered.append(kw['subscription_info']['endpoint']))
    assert push._enviar_a_dispositivos({'categoria': 'chats'})['enviadas'] == 2
    assert delivered == ['luis', 'teresa']
    delivered.clear()
    assert push._enviar_a_dispositivos({'categoria': 'alertas'})['enviadas'] == 2
    assert delivered == ['alexander', 'teresa']
    with pytest.raises(ValueError): prefs.guardar('alexander', 'invalid')


def test_panel_send_concurrent_retry_and_content_mismatch():
    calls = []
    async def run():
        gate = asyncio.Event()
        @send_once.envio_unico
        async def responder(telefono, body, usuario):
            calls.append(body['mensaje']); await gate.wait(); return {'status': 'ok'}
        args = ('507', {'request_id': 'id', 'mensaje': 'Hola'}, 'alexander')
        first = asyncio.create_task(responder(*args)); await asyncio.sleep(0)
        with pytest.raises(HTTPException) as pending: await responder(*args)
        assert pending.value.status_code == 409
        gate.set(); assert await first == {'status': 'ok'}
        assert await responder(*args) == {'status': 'ok'}
        with pytest.raises(HTTPException): await responder('507', {'request_id': 'id', 'mensaje': 'Otro'}, 'alexander')
        assert calls == ['Hola']
    asyncio.run(run())


def test_uncertain_send_not_repeated():
    calls = []
    @send_once.envio_unico
    async def responder(telefono, body, usuario):
        calls.append(1); raise RuntimeError('connection lost after send')
    async def run():
        args = ('507', {'request_id': 'uncertain', 'mensaje': 'Hola'}, 'alexander')
        with pytest.raises(RuntimeError): await responder(*args)
        with pytest.raises(HTTPException): await responder(*args)
    asyncio.run(run()); assert calls == [1]


def test_generated_identical_paragraph_sent_once(monkeypatch):
    from app.api import whatsapp
    deliver = AsyncMock(return_value=SimpleNamespace(is_success=True))
    monkeypatch.setattr(whatsapp, 'enviar_mensaje_whatsapp', deliver)
    monkeypatch.setattr(whatsapp.asyncio, 'sleep', AsyncMock())
    asyncio.run(whatsapp.enviar_respuesta_natural('507', 'Hola, ¿cómo estás?\n\nHola, ¿cómo estás?', ''))
    deliver.assert_awaited_once_with('507', 'Hola, ¿cómo estás?')


def test_panel_routes_preferences_auth_and_assisted_send_retry(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import panel
    app = FastAPI(); app.include_router(panel.router)
    app.dependency_overrides[panel.verificar_credenciales_panel] = lambda: 'alexander'
    monkeypatch.setattr(panel, 'obtener_sesion_existente', lambda tel: SimpleNamespace(obtener_historial=lambda: [{'role': 'user', 'content': 'Hola'}]))
    monkeypatch.setattr(panel, '_validar_operador_conversacion', lambda *args: None)
    monkeypatch.setattr(panel, 'redactar_respuesta_de_asesor', lambda *args: 'Hola, ¿cómo estás?')
    delivery = AsyncMock(return_value=SimpleNamespace(is_success=True))
    monkeypatch.setattr(panel, 'enviar_respuesta_natural', delivery)
    monkeypatch.setattr(panel, 'agregar_al_historial', lambda *args, **kwargs: None)
    monkeypatch.setattr(panel, 'extraer_id_mensaje_meta', lambda response: 'wamid.test')
    monkeypatch.setattr(panel, 'actualizar_sesion', lambda *args, **kwargs: None)
    with TestClient(app) as client:
        assert client.get('/panel/notificaciones/preferencias').json() == {'categoria': 'ambos'}
        assert client.put('/panel/notificaciones/preferencias', json={'categoria': 'chats'}).status_code == 200
        assert client.get('/panel/notificaciones/preferencias').json() == {'categoria': 'chats'}
        assert client.put('/panel/notificaciones/preferencias', json={'categoria': 'invalid'}).status_code == 422
        payload = {'mensaje': 'Saluda', 'request_id': 'route-test'}
        assert client.post('/panel/responder/507', json=payload).status_code == 200
        assert client.post('/panel/responder/507', json=payload).status_code == 200
        assert delivery.await_count == 1
        assert delivery.await_args.kwargs == {"message_id": "", "simular_escritura": False, "dividir": False}
        assert client.get('/panel/alertas/paquetes').json() == []
        app.dependency_overrides.clear()
        assert client.get('/panel/notificaciones/preferencias').status_code == 401


def test_daily_recheck_fetches_once_per_tracking_and_resolves(monkeypatch):
    from app.tools import ptyfreight
    packages.observar('T', '507', result(), NOW)
    packages.observar('T', '508', result(), NOW)
    calls = []
    monkeypatch.setattr(ptyfreight, 'consultar_tracking', lambda tracking: (calls.append(tracking) or result(ubicacion='Panamá')))
    ptyfreight._cache_tracking['T'] = {'stale': True}
    asyncio.run(packages.revisar_trackings())
    assert calls == ['T']
    assert 'T' not in ptyfreight._cache_tracking
    assert packages.listar_alertas(NOW) == []


def test_daily_scheduler_at_nine_panama(monkeypatch):
    from app import scheduler as jobs
    entries = []
    fake = SimpleNamespace(add_job=lambda func, trigger, **kwargs: entries.append((func, trigger, kwargs)), start=lambda: None)
    monkeypatch.setattr(jobs, 'scheduler', fake)
    jobs.iniciar_scheduler()
    job = next(row for row in entries if row[2]['id'] == 'revisar_demoras_tracking')
    assert job[0] is packages.revisar_trackings
    assert str(job[1].timezone) == 'America/Panama'
    assert 'hour=\'9\'' in str(job[1])
    assert job[2]['max_instances'] == 1


def test_panel_response_has_no_typing_delay_and_one_whatsapp_send(monkeypatch):
    from app.api import whatsapp
    delivery = AsyncMock(return_value=SimpleNamespace(is_success=True))
    sleep = AsyncMock()
    monkeypatch.setattr(whatsapp, 'enviar_mensaje_whatsapp', delivery)
    monkeypatch.setattr(whatsapp.asyncio, 'sleep', sleep)
    texto = 'Primera parte\n\nSegunda parte\n\nTercera parte'
    asyncio.run(whatsapp.enviar_respuesta_natural('507', texto, '', simular_escritura=False, dividir=False))
    delivery.assert_awaited_once_with('507', texto)
    sleep.assert_not_awaited()
