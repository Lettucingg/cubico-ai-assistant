from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock,Mock
import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.api import panel
from app.services import outbound_templates as service,panel_send_once,cost_analytics
from app.services import delivery_diagnostics
from app.db import session_store as store
from app.ai.orchestrator import normalizar_historial_para_claude

TEMPLATE={'name':'cubico_tarifa_preferencial_210','language':'es_PA','status':'APPROVED','category':'MARKETING',
          'components':[{'type':'HEADER','format':'IMAGE'},{'type':'BODY','text':'Hola {{1}}, trae tus compras por $2.10.'},
                        {'type':'BUTTONS','buttons':[{'type':'URL','text':'Registrarme','url':'https://cubico.com.pa/entrar/?promo=SOMOSCUBICO'}]}]}


@pytest.fixture
def setup(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'newchat.db'),connect_args={'check_same_thread':False})
    store.BaseSesiones.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    for module in (store,panel_send_once,cost_analytics,delivery_diagnostics):monkeypatch.setattr(module,'SessionSesiones',factory)
    row=service.describe(TEMPLATE)
    lookup=AsyncMock(return_value=[row]);monkeypatch.setattr(service,'list_templates',lookup)
    upload=AsyncMock(return_value='test-media');send=AsyncMock(return_value=httpx.Response(200,json={'messages':[{'id':'wamid-new'}]}))
    monkeypatch.setattr(panel,'subir_media_whatsapp',upload);monkeypatch.setattr(panel,'enviar_plantilla_whatsapp',send)
    app=FastAPI();app.include_router(panel.router)
    app.dependency_overrides[panel.verificar_credenciales_panel]=lambda:'alexander'
    yield NS(client=TestClient(app),row=row,lookup=lookup,send=send,upload=upload,app=app)
    engine.dispose()


def body(row,**updates):return {'request_id':'request-test-1','plantilla':row['nombre'],'idioma':row['idioma'],
                              'huella':row['huella'],'valores':['Persona de prueba'],'permiso_contacto':True,**updates}


def test_unknown_number_creates_only_chat_with_actual_template_and_context(setup):
    assert store.obtener_sesion_existente('50760000000') is None
    response=setup.client.post('/panel/iniciar-chat/60000000',json=body(setup.row))
    assert response.status_code==200,response.text
    assert response.json()['telefono']=='50760000000'
    setup.send.assert_awaited_once()
    components=setup.send.call_args.args[2]
    assert components[0]['parameters'][0]['image']['id']=='test-media'
    assert components[1]['parameters'][0]['text']=='Persona de prueba'
    assert not any(c['type']=='button' for c in components) # Fixed URL inherited from Meta.
    session=store.obtener_sesion_existente('50760000000')
    assert session.codigo_cliente_verificado is None and not session.atencion_humana_directa
    message=session.obtener_historial()[0]
    assert '$2.10' in message['content'] and 'promo=SOMOSCUBICO' in message['content']
    assert message['autor_tipo']=='plantilla' and message['operador']=='alexander'
    assert message['whatsapp_message_id']=='wamid-new'
    actual=normalizar_historial_para_claude(session.obtener_historial(),'¿Cómo me registro?')
    assert 'promo=SOMOSCUBICO' in str(actual) and 'Persona de prueba' in str(actual)
    assert 'no es una verificación' in str(actual)


def test_duplicate_request_never_sends_twice_and_changed_payload_conflicts(setup):
    for _ in range(2):assert setup.client.post('/panel/iniciar-chat/60000000',json=body(setup.row)).status_code==200
    setup.send.assert_awaited_once()
    assert len(store.obtener_sesion_existente('50760000000').obtener_historial())==1
    changed=setup.client.post('/panel/iniciar-chat/60000000',json=body(setup.row,valores=['Otra persona']))
    assert changed.status_code==409
    setup.send.assert_awaited_once()


def test_failure_receipt_before_http_response_is_reconciled_in_history(setup):
    async def send(*args,**kwargs):
        cost_analytics.record_whatsapp_receipts({'entry':[{'changes':[{'value':{'statuses':[{
            'id':'wamid-early','recipient_id':'50760000000','status':'failed',
            'errors':[{'code':130472,'error_data':{'details':'Provider experiment restriction'}}]}]}}]}]})
        return httpx.Response(200,json={'messages':[{'id':'wamid-early'}]})
    setup.send.side_effect=send
    result=setup.client.post('/panel/iniciar-chat/60000000',json=body(setup.row))
    assert result.status_code==200 and result.json()['estado']=='failed'
    history=store.obtener_sesion_existente('50760000000').obtener_historial()
    assert history[0]['estado_entrega']=='failed' and history[0]['error_entrega']=='Provider experiment restriction'


def test_unknown_contact_still_requires_auth_consent_approved_preview_and_variables(setup):
    setup.app.dependency_overrides.clear()
    assert setup.client.get('/panel/iniciar-chat/plantillas').status_code==401
    assert setup.client.post('/panel/iniciar-chat/60000000',json=body(setup.row)).status_code==401
    setup.app.dependency_overrides[panel.verificar_credenciales_panel]=lambda:'alexander'
    for changes in ({'permiso_contacto':False},{'valores':[]},{'valores':['']},{'request_id':''}):
        assert setup.client.post('/panel/iniciar-chat/60000000',json=body(setup.row,**changes)).status_code==422
    stale=setup.client.post('/panel/iniciar-chat/60000000',json=body(setup.row,huella='0'*64))
    assert stale.status_code==409
    assert setup.client.post('/panel/iniciar-chat/not-a-number',json=body(setup.row)).status_code==422
    setup.send.assert_not_awaited()
    assert store.obtener_sesion_existente('50760000000') is None


def test_operator_lock_and_failed_send_do_not_create_fake_history(setup):
    store.obtener_o_crear_sesion('50760000000')
    store.actualizar_sesion('50760000000',atencion_humana_directa=True,atencion_humana_por='teresa')
    assert setup.client.post('/panel/iniciar-chat/60000000',json=body(setup.row)).status_code==409
    setup.send.assert_not_awaited()
    setup.send.side_effect=httpx.ReadTimeout('ambiguous')
    for _ in range(2):
        response=setup.client.post('/panel/iniciar-chat/61111111',json=body(setup.row))
        assert response.status_code in (502,409)
    setup.send.assert_awaited_once()
    assert store.obtener_sesion_existente('50761111111').obtener_historial()==[]


@pytest.mark.parametrize('status',['REJECTED','PENDING','PAUSED','DISABLED'])
def test_nonapproved_templates_never_listed(status):assert service.describe({**TEMPLATE,'status':status}) is None


def test_unsupported_or_dynamic_components_are_not_offered():
    dynamic=deepcopy(TEMPLATE);dynamic['components'][-1]['buttons'][0]['url']='https://example.com/{{1}}'
    assert service.describe(dynamic) is None
    document=deepcopy(TEMPLATE);document['components'][0]['format']='DOCUMENT'
    assert service.describe(document) is None
    named=deepcopy(TEMPLATE);named['components'][1]['text']='Hola {{name}}'
    assert service.describe(named) is None


def test_meta_pagination_only_approved_and_fixed_host(monkeypatch):
    monkeypatch.setattr(service.settings,'WHATSAPP_BUSINESS_ACCOUNT_ID','1234')
    original=httpx.AsyncClient;calls=[]
    def handler(request):
        calls.append(request)
        assert str(request.url).startswith('https://graph.facebook.com/v21.0/1234/message_templates')
        if len(calls)==1:return httpx.Response(200,json={'data':[{**TEMPLATE,'status':'PENDING'}],
             'paging':{'next':'https://untrusted.invalid/do-not-follow','cursors':{'after':'cursor2'}}})
        assert request.url.params['after']=='cursor2'
        return httpx.Response(200,json={'data':[TEMPLATE]})
    monkeypatch.setattr(service.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    import asyncio
    assert asyncio.run(service.list_templates())[0]['nombre']==TEMPLATE['name']
    assert len(calls)==2
