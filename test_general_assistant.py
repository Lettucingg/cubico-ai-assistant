import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api import panel
from app.services import internal_assistant as service, payment_policy


def model(monkeypatch):
    from app.ai import orchestrator
    from app.services import cost_analytics
    client=Mock(); client.with_options.return_value=client
    monkeypatch.setattr(orchestrator,'cliente_claude',client)
    call=Mock(return_value=SimpleNamespace(content=[SimpleNamespace(type='text',text=json.dumps({'respuesta':'Explicación interna','borrador':'Respuesta para revisar'}))]))
    monkeypatch.setattr(cost_analytics,'call_anthropic',call)
    monkeypatch.setattr(service,'active_context',lambda *_:[])
    monkeypatch.setattr(service,'verified_location',lambda:None)
    for name in ('consultar_facturas_por_codigo','consultar_paquetes_por_codigo','consultar_ultimo_pago_por_codigo'):
        monkeypatch.setattr(service,name,Mock(side_effect=AssertionError('No customer sources in general mode')))
    return call


@pytest.mark.parametrize('question',[
    '¿Qué formas de pago tenemos?', '¿Aceptan Yappy?', '¿Cuál es el horario?',
    '¿Dónde queda el local?', '¿Hay reparto disponible?', '¿Cómo funciona un casillero?',
    '¿Qué condiciones tiene SOMOSCUBICO?', '¿Cuándo vence la promoción?',
    '¿La promoción sirve para China?', 'Ya tengo cuenta, ¿puedo cambiar mi tarifa?',
    '¿Por qué Amazon cambia mi dirección?', '¿Me cobrarán impuestos?',
    '¿Puedo usar solo cinco dígitos del ZIP?', 'Dice OCEAN, ¿es marítimo?',
    '¿Qué significa Standard Shipping?', '¿Puede retirar otra persona?',
    'Quiero dejar de recibir publicidad', 'Quiero borrar mis datos',
    '¿Tienen teléfono para llamar?', '¿Cómo cotizo un envío aéreo?',
])
def test_general_questions_are_private_bounded_and_do_not_query_customer(question,monkeypatch):
    call=model(monkeypatch)
    result=service.query_general(question,'consulta')
    assert result['telefono'] is None and result['privado'] and not result['enviado']
    assert result['borrador']==''
    args=call.call_args.kwargs
    assert args['task']=='asistente_interno' and 'tools' not in args
    assert args['max_tokens']==1400
    assert 'NO acepta Yappy' in args['system']
    assert 'No hay cliente vinculado' in args['system']
    assert result['datos']['campana']['estado']=='preparada_pendiente_de_activacion'


def test_general_draft_and_bad_model_response(monkeypatch):
    call=model(monkeypatch)
    assert service.query_general('Ayúdame a responder','borrador')['borrador']=='Respuesta para revisar'
    call.return_value.content[0].text='invalid'
    with pytest.raises(ValueError,match='No se envió nada'):
        service.query_general('otra consulta')


def test_general_tracking_uses_public_lookup_only(monkeypatch):
    monkeypatch.setattr(service,'extract_trackings',lambda _:['TRACK123456'])
    lookup=Mock(return_value={'telefono':None,'privado':True})
    monkeypatch.setattr(service,'lookup_tracking',lookup)
    assert service.query_general('TRACK123456','borrador')['telefono'] is None
    assert lookup.call_args.args[0].telefono is None
    assert lookup.call_args.args[2]=='borrador'


def test_yappy_requires_flag_and_configured_number(monkeypatch):
    monkeypatch.setattr(payment_policy.settings,'CUBICO_PAYMENT_YAPPY','old-private-number')
    monkeypatch.setattr(payment_policy.settings,'CUBICO_YAPPY_ENABLED',False)
    assert 'old-private-number' not in payment_policy.payment_rules()
    assert 'no acepta' in payment_policy.yappy_reply()
    monkeypatch.setattr(payment_policy.settings,'CUBICO_YAPPY_ENABLED',True)
    assert 'old-private-number' in payment_policy.yappy_reply()
    monkeypatch.setattr(payment_policy.settings,'CUBICO_PAYMENT_YAPPY','')
    assert 'no acepta' in payment_policy.yappy_reply()


def test_general_endpoint_auth_validation_failure_and_no_session_lookup(monkeypatch):
    app=FastAPI();app.include_router(panel.router)
    client=TestClient(app)
    assert client.post('/panel/asistente',json={'pregunta':'Hola'}).status_code==401
    app.dependency_overrides[panel.verificar_credenciales_panel]=lambda:'alexander'
    monkeypatch.setattr(panel,'obtener_sesion_existente',Mock(side_effect=AssertionError('No session required')))
    query=Mock(return_value={'telefono':None,'privado':True,'enviado':False})
    monkeypatch.setattr(service,'query_general',query)
    assert client.post('/panel/asistente',json={'pregunta':'  '}).status_code==422
    assert client.post('/panel/asistente',json={'pregunta':'x'*2001}).status_code==422
    assert client.post('/panel/asistente',json={'pregunta':'Pagos'}).json()['enviado'] is False
    query.side_effect=RuntimeError('private-secret')
    response=client.post('/panel/asistente',json={'pregunta':'Pagos'})
    assert response.status_code==502 and 'private-secret' not in response.text


def test_actual_quick_replies_and_assistant_payment_evidence(monkeypatch):
    from app.ai import orchestrator
    monkeypatch.setattr(payment_policy.settings,'CUBICO_YAPPY_ENABLED',False)
    monkeypatch.setattr(payment_policy.settings,'CUBICO_PAYMENT_YAPPY','do-not-publish')
    reply=orchestrator.buscar_respuesta_fija('¿Aceptan Yappy?')
    assert 'no acepta Yappy' in reply and 'do-not-publish' not in reply
    assert 'no acepta Yappy' in orchestrator.buscar_respuesta_fija('¿Están en el directorio de Yappy?')
    hours=orchestrator.buscar_respuesta_fija('¿Qué horario tienen?')
    assert '10:00 am' in hours and '1:00 pm' in hours and '9:00' not in hours


def test_operational_source_failure_not_zero(monkeypatch):
    call=model(monkeypatch)
    from app.services import staff_overview
    monkeypatch.setattr(staff_overview,'summary',Mock(side_effect=RuntimeError('secret')))
    result=service.query_general('Dame el resumen operativo')
    source=result['datos']['resumen_operativo']
    assert not source['disponible'] and 'secret' not in str(source) and 'cero' in source['error']
