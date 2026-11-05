import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import session_store as store
from app.services import campaign_pilot as pilot, marketing_preferences as preferences
from app.services import cost_analytics, delivery_diagnostics
from app.services.outbound_templates import describe

NOW = datetime(2026, 11, 5, 14)
TEMPLATE = describe({'name': pilot.PROMOTION, 'language': 'es_PA', 'status': 'APPROVED', 'category': 'MARKETING',
    'components': [{'type': 'HEADER', 'format': 'IMAGE'}, {'type': 'BODY', 'text': 'Hola {{1}}, Miami a $2.10.'},
                   {'type': 'BUTTONS', 'buttons': [{'type': 'URL', 'text': 'Registro', 'url': 'https://cubico.com.pa/entrar/?promo=SOMOSCUBICO'}]}]})


@pytest.fixture
def setup(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'pilot.db'), connect_args={'check_same_thread': False})
    store.BaseSesiones.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    for module in (store, pilot, preferences, cost_analytics, delivery_diagnostics):
        monkeypatch.setattr(module, 'SessionSesiones', factory)
    monkeypatch.setattr(pilot, 'now_utc', lambda: NOW)
    monkeypatch.setattr(pilot, 'current_template', AsyncMock(return_value=TEMPLATE))
    send = AsyncMock(return_value={'estado': 'accepted', 'message_id': 'wamid-pilot'})
    monkeypatch.setattr(pilot, 'send_recipient', send)
    yield factory, send
    engine.dispose()


def source(count=12):
    return [{'nombre': f'Prueba {i}', 'telefono': str(60000000 + i), 'campana': pilot.CAMPAIGN, 'nota': ''} for i in range(count)]


def prepare(rows=None, **kwargs):
    return asyncio.run(pilot.prepare('piloto', source() if rows is None else rows, 'alexander', permission=True, **kwargs))


def activate():
    return asyncio.run(pilot.activate('piloto', NOW.replace(tzinfo=timezone.utc)))


def test_prepare_paused_maximum_ten_no_send_and_idempotent(setup):
    factory, send = setup
    result = prepare()
    assert result['estado'] == 'pausada' and result['resumen'] == {'pendiente': 10}
    assert 'promo=SOMOSCUBICO' in result['vista_previa']
    asyncio.run(pilot.run_due()); prepare()
    send.assert_not_awaited()
    with factory() as db:
        assert db.query(pilot.PilotRecipient).count() == 10
    with pytest.raises(ValueError): prepare(count=11)
    with pytest.raises(ValueError): asyncio.run(pilot.prepare('otra', source(), 'alexander'))


def test_source_exclusions(setup):
    rows = source(9)
    rows += [{**rows[0]}, {**rows[1], 'campana': 'S2N_REDIRECCION'}]
    rows[2]['nota'] = 'SACADO'
    rows[3]['campana'] = 'SOMOSCUBICO_EMAIL'
    rows[4]['telefono'] = ''
    preferences.suppress('60000005')
    store.obtener_o_crear_sesion('50760000006')
    store.actualizar_sesion('50760000006', atencion_humana_directa=True)
    eligible, excluded = pilot.candidates(rows)
    assert [r['telefono'] for r in eligible] == ['50760000000', '50760000007', '50760000008']
    assert sum(excluded.values()) == len(rows) - len(eligible)


def test_reservations_shared_between_batches(setup):
    prepare()
    with pytest.raises(ValueError, match='Solo hay 2'):
        asyncio.run(pilot.prepare('otra', source(), 'alexander', permission=True))


def test_due_time_and_one_attempt_per_minute(setup, monkeypatch):
    factory, send = setup
    prepare()
    asyncio.run(pilot.activate('piloto', (NOW + timedelta(minutes=2)).replace(tzinfo=timezone.utc)))
    asyncio.run(pilot.run_due()); send.assert_not_awaited()
    monkeypatch.setattr(pilot, 'now_utc', lambda: NOW + timedelta(minutes=2))
    asyncio.run(pilot.run_due()); asyncio.run(pilot.run_due())
    assert send.await_count == 1
    monkeypatch.setattr(pilot, 'now_utc', lambda: NOW + timedelta(minutes=3))
    asyncio.run(pilot.run_due())
    assert send.await_count == 2
    assert send.call_args_list[0].args[4] != send.call_args_list[1].args[4]


def test_optout_after_preparation_skips_send(setup):
    _, send = setup
    prepare(); activate(); preferences.suppress('60000000')
    asyncio.run(pilot.run_due()); send.assert_not_awaited()
    assert pilot.report('piloto')['resumen']['omitida'] == 1


def test_changed_template_pauses(setup, monkeypatch):
    _, send = setup
    prepare(); activate()
    monkeypatch.setattr(pilot, 'current_template', AsyncMock(return_value={**TEMPLATE, 'huella': 'changed'}))
    asyncio.run(pilot.run_due())
    assert pilot.report('piloto')['estado'] == 'pausada'
    send.assert_not_awaited()
    with pytest.raises(ValueError, match='cambió'): activate()


def test_timeout_pauses_never_retries(setup):
    _, send = setup
    prepare(); activate(); send.side_effect = TimeoutError()
    asyncio.run(pilot.run_due()); asyncio.run(pilot.run_due())
    assert pilot.report('piloto')['estado'] == 'pausada'
    assert pilot.report('piloto')['resumen']['incierta'] == 1
    activate(); asyncio.run(pilot.run_due())
    assert send.await_count == 1


def test_expired_window_not_sent_late(setup, monkeypatch):
    _, send = setup
    prepare(); activate()
    monkeypatch.setattr(pilot, 'now_utc', lambda: NOW + timedelta(hours=2))
    asyncio.run(pilot.run_due())
    assert pilot.report('piloto')['estado'] == 'vencida'
    send.assert_not_awaited()


def test_claimed_crash_never_requeues(setup):
    factory, send = setup
    prepare(); activate()
    with factory() as db:
        row = db.query(pilot.PilotRecipient).first()
        row.estado = 'en_proceso'; row.intento_en = NOW - timedelta(minutes=6); db.commit()
    asyncio.run(pilot.run_due())
    assert pilot.report('piloto')['estado'] == 'pausada'
    send.assert_not_awaited()


def test_delivery_evidence_and_meta_codes(setup):
    factory, _ = setup
    prepare(); activate(); asyncio.run(pilot.run_due())
    assert pilot.report('piloto')['resumen']['accepted'] == 1
    delivery_diagnostics.record_receipt({'id': 'wamid-pilot', 'recipient_id': '50760000000', 'status': 'failed',
        'errors': [{'code': 130472, 'message': 'experiment'}]})
    result = pilot.report('piloto')
    assert result['resumen']['failed'] == 1
    assert result['destinatarios'][0]['codigos_meta'] == ['130472']


def test_optout_detection_and_persistence(setup):
    for text in ('BAJA', 'Stop!', 'No me manden más mensajes', 'Por favor, darme de baja'):
        assert preferences.requests_optout(text)
    for text in ('la tarifa baja', 'cuanto cuesta', 'no quiero cancelar mi pedido', 'si la tasa baja compro'):
        assert not preferences.requests_optout(text)
    assert preferences.suppress('60000000')
    assert not preferences.suppress('50760000000')
    assert preferences.is_suppressed('60000000')


def test_three_meta_failures_pause_remaining_queue(setup):
    factory, send = setup
    prepare(); activate()
    with factory() as db:
        for index, row in enumerate(db.query(pilot.PilotRecipient).limit(3)):
            row.estado='accepted';row.message_id=f'failed-{index}'
            db.add(delivery_diagnostics.MetaDeliveryReceipt(dedupe_key=f'failure-{index}',message_id=row.message_id,
                phone=row.telefono,status='failed',errors_json='[{"code":"131049"}]'))
        db.commit()
    asyncio.run(pilot.run_due())
    assert pilot.report('piloto')['estado']=='pausada'
    assert pilot.report('piloto')['resumen']['pendiente']==7
    send.assert_not_awaited()


def test_pause_during_template_lookup_prevents_claim(setup,monkeypatch):
    _,send=setup
    prepare();activate()
    async def lookup():
        pilot.pause('piloto')
        return TEMPLATE
    monkeypatch.setattr(pilot,'current_template',lookup)
    asyncio.run(pilot.run_due())
    send.assert_not_awaited()


def test_incoming_optout_is_saved_without_ai_and_acknowledged_once(setup,monkeypatch):
    import httpx
    from app.api import whatsapp
    notify=AsyncMock();send=AsyncMock(return_value=httpx.Response(200,json={'messages':[{'id':'ack'}]}))
    generate=AsyncMock()
    monkeypatch.setattr(whatsapp,'notificar_equipo_escalamiento',notify)
    monkeypatch.setattr(whatsapp,'enviar_mensaje_whatsapp',send)
    monkeypatch.setattr(whatsapp,'generar_respuesta',generate)
    message={'telefono':'50760000000','tipo':'text','texto':'BAJA','message_id':'incoming-baja'}
    asyncio.run(whatsapp._procesar_mensaje_en_segundo_plano_sin_candado(message))
    asyncio.run(whatsapp._procesar_mensaje_en_segundo_plano_sin_candado(message))
    assert preferences.is_suppressed(message['telefono'])
    assert send.await_count==1 and notify.await_count==1
    generate.assert_not_called()
