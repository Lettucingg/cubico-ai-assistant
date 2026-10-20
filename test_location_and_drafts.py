import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock
import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import session_store as store
from app.services import business_location as loc, panel_send_once
from app.api import panel
from app.ai import orchestrator as bot

@pytest.fixture
def isolated(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'local.db'))
    store.BaseSesiones.metadata.create_all(engine)
    factory=sessionmaker(bind=engine)
    monkeypatch.setattr(store,'SessionSesiones',factory)
    monkeypatch.setattr(panel_send_once,'SessionSesiones',factory)
    yield factory
    engine.dispose()

def pin(**updates):
    return {'direccion':'Local de prueba','enlace':'https://maps.app.goo.gl/test-pin',
            'latitud':None,'longitud':None,'confirmada':True,**updates}

def test_saved_link_is_shared_by_bot_preview_and_sender(isolated,monkeypatch):
    loc.save_location(pin(),'alexander')
    assert loc.verified_location()['enlace']==pin()['enlace']
    assert pin()['enlace'] in loc.location_rules()
    assert loc.native_location() is None
    point=loc.location_preview();assert point['tipo']=='enlace'
    monkeypatch.setattr(panel,'_validar_operador_conversacion',lambda *a,**kw:object())
    sent=AsyncMock(return_value=httpx.Response(200,json={'messages':[{'id':'wamid-link'}]}))
    native=AsyncMock();history=Mock()
    monkeypatch.setattr(panel,'enviar_mensaje_whatsapp',sent)
    monkeypatch.setattr(panel,'enviar_ubicacion_whatsapp',native)
    monkeypatch.setattr(panel,'agregar_al_historial',history)
    body={'mensaje':point['revision'],'request_id':'link-1'}
    for _ in range(2):asyncio.run(panel.enviar_ubicacion_desde_panel('5071',body,'alexander'))
    sent.assert_awaited_once();native.assert_not_called()
    assert pin()['enlace'] in sent.call_args.args[1]
    assert history.call_args.kwargs['estado_entrega']=='accepted'
    # Explicit deactivation takes precedence over any old environment pin.
    loc.save_location(pin(confirmada=False),'teresa')
    assert loc.verified_location() is None and loc.location_preview() is None

def test_native_pin_coordinates_and_stale_previews(isolated,monkeypatch):
    loc.save_location(pin(latitud=8.99,longitud=-79.5),'alexander')
    point=loc.location_preview();assert point['tipo']=='location'
    assert point['ubicacion']['latitude']==8.99
    loc.save_location(pin(latitud=9,longitud=-79.51),'alexander')
    monkeypatch.setattr(panel,'_validar_operador_conversacion',lambda *a,**kw:object())
    sent=AsyncMock();monkeypatch.setattr(panel,'enviar_ubicacion_whatsapp',sent)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(panel.enviar_ubicacion_desde_panel('5071',{'mensaje':point['revision'],'request_id':'stale'},'alexander'))
    assert exc.value.status_code==409;sent.assert_not_called()

@pytest.mark.parametrize('changes',[{'enlace':'javascript:alert(1)'},{'enlace':'https://maps.app.goo.gl.evil.test/pin'},
                                   {'latitud':9},{'latitud':float('nan'),'longitud':1}])
def test_invalid_location_not_saved(isolated,changes):
    with pytest.raises(ValueError):loc.save_location(pin(**changes),'alexander')
    with isolated() as db:assert db.get(store.UbicacionLocal,1) is None

def test_new_routes_require_authentication():
    app=FastAPI();app.include_router(panel.router)
    with TestClient(app) as client:
        assert client.get('/panel/configuracion/ubicacion').status_code==401
        assert client.put('/panel/configuracion/ubicacion',json=pin()).status_code==401
        assert client.post('/panel/mejorar-borrador/5071',json={'mensaje':'Hola'}).status_code==401
        assert client.post('/panel/enviar-texto/5071',json={'mensaje':'Hola'}).status_code==401

def test_exact_text_does_not_invoke_ai_or_clear_attention(isolated,monkeypatch):
    monkeypatch.setattr(panel,'_validar_operador_conversacion',lambda *a,**kw:object())
    redact=Mock(side_effect=AssertionError('No implicit AI rewrite'))
    send=AsyncMock(return_value=httpx.Response(200,json={'messages':[{'id':'wamid-exact'}]}))
    history=Mock();update=Mock()
    monkeypatch.setattr(panel,'redactar_respuesta_de_asesor',redact)
    monkeypatch.setattr(panel,'enviar_respuesta_natural',send)
    monkeypatch.setattr(panel,'agregar_al_historial',history)
    monkeypatch.setattr(panel,'actualizar_sesion',update)
    body={'mensaje':'Aquí está el punto confirmado.','request_id':'exact-1','asistido':True}
    for _ in range(2):asyncio.run(panel.enviar_texto_revisado('5071',body,'alexander'))
    send.assert_awaited_once_with('5071',body['mensaje'],message_id='',simular_escritura=False,dividir=False)
    redact.assert_not_called();update.assert_not_called()
    assert history.call_args.kwargs['modo_envio']=='revisado_bruno'

def test_draft_endpoint_never_sends_and_rejects_new_messages(monkeypatch):
    messages=[{'role':'user','content':'Dónde queda la bodega para retiro'}]
    session=SimpleNamespace(obtener_historial=lambda:list(messages))
    monkeypatch.setattr(panel,'_validar_operador_conversacion',lambda *a,**kw:session)
    redact=Mock(return_value='El retiro se coordina con Teresa.')
    sent=AsyncMock(side_effect=AssertionError('Draft cannot send'))
    monkeypatch.setattr(panel,'redactar_respuesta_de_asesor',redact)
    monkeypatch.setattr(panel,'enviar_respuesta_natural',sent)
    result=asyncio.run(panel.mejorar_borrador('5071',panel.BorradorAsistidoPayload(mensaje='Coordina con Teresa'),'alexander'))
    assert result['enviado'] is False;sent.assert_not_called()
    def changed(*_):messages.append({'role':'user','content':'Tengo otra pregunta'});return 'viejo'
    redact.side_effect=changed
    with pytest.raises(HTTPException) as exc:
        asyncio.run(panel.mejorar_borrador('5071',panel.BorradorAsistidoPayload(mensaje='Coordina'),'alexander'))
    assert exc.value.status_code==409

def test_editor_receives_recent_history_without_claiming_review(monkeypatch,isolated):
    history=[{'role':'user','content':'Quiero retirar y necesito la ubicación'},
             {'role':'humano','content':'Hola, ¿en qué te ayudo?','estado_entrega':'read'},
             {'role':'humano','content':'Punto anterior','estado_entrega':'failed'}]
    monkeypatch.setattr(bot,'obtener_sesion_existente',lambda _:SimpleNamespace(obtener_historial=lambda:history))
    model=Mock(return_value=SimpleNamespace(content=[SimpleNamespace(type='text',text='Coordina el retiro con Teresa.')]))
    monkeypatch.setattr(bot,'call_anthropic',model)
    monkeypatch.setattr(bot,'active_context',lambda _:[])
    assert bot.redactar_respuesta_de_asesor('ubicación','Coordina con Teresa','5071')=='Coordina el retiro con Teresa.'
    prompt=model.call_args.kwargs['messages'][0]['content']
    assert 'Quiero retirar' in prompt and 'failed' in prompt
    assert 'El equipo ya revisó internamente' not in prompt
    assert 'No añadas saludos' in prompt

def test_location_changes_reach_model_without_restart(isolated,monkeypatch):
    model=Mock(return_value=SimpleNamespace(stop_reason='end_turn',content=[SimpleNamespace(type='text',text='Con gusto.')]))
    monkeypatch.setattr(bot,'call_anthropic',model)
    monkeypatch.setattr(bot,'active_context',lambda *a:[])
    loc.save_location(pin(direccion='LOCAL_UNO_PRUEBA'),'alexander')
    assert bot.generar_respuesta('¿Qué servicios ofrecen?','5071')=='Con gusto.'
    first=str(model.call_args.kwargs['system']);assert 'LOCAL_UNO_PRUEBA' in first
    loc.save_location(pin(direccion='LOCAL_DOS_PRUEBA',enlace='https://maps.app.goo.gl/new-pin'),'alexander')
    bot.generar_respuesta('¿Qué servicios ofrecen?','5071')
    second=str(model.call_args.kwargs['system']);assert 'LOCAL_DOS_PRUEBA' in second and 'LOCAL_UNO_PRUEBA' not in second
