import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import httpx
import pytest
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.services import business_location as loc, panel_send_once
from app.api import panel, whatsapp
from app.db import session_store as store

@pytest.fixture
def configured(monkeypatch):
    for key,value in {'CUBICO_LOCATION_VERIFIED':True,'CUBICO_LOCAL_ADDRESS':'Dirección de prueba',
                      'CUBICO_LOCATION_URL':'https://maps.app.goo.gl/test-pin',
                      'CUBICO_LOCATION_LATITUDE':'8.98','CUBICO_LOCATION_LONGITUDE':'-79.52'}.items():
        monkeypatch.setattr(loc.settings,key,value)
    return loc.native_location()

@pytest.mark.parametrize('key,value', [('CUBICO_LOCATION_VERIFIED',False),('CUBICO_LOCATION_LATITUDE',''),
    ('CUBICO_LOCATION_LATITUDE','nan'),('CUBICO_LOCATION_LONGITUDE','inf'),
    ('CUBICO_LOCATION_LATITUDE','91'),('CUBICO_LOCATION_LONGITUDE','-181'),
    ('CUBICO_LOCATION_URL','https://example.com/old'),('CUBICO_LOCAL_ADDRESS','')])
def test_invalid_or_unconfirmed_pin_is_unavailable(configured,monkeypatch,key,value):
    monkeypatch.setattr(loc.settings,key,value)
    assert loc.native_location() is None

@pytest.fixture
def api(configured,monkeypatch,tmp_path):
    current=SimpleNamespace(atencion_humana_directa=True,atencion_humana_por='alexander')
    monkeypatch.setattr(panel,'obtener_sesion_existente',lambda _:current)
    sent=AsyncMock(return_value=httpx.Response(200,json={'messages':[{'id':'wamid-location'}]}))
    monkeypatch.setattr(panel,'enviar_ubicacion_whatsapp',sent)
    engine=create_engine('sqlite:///'+str(tmp_path/'history.db'))
    store.BaseSesiones.metadata.create_all(engine)
    factory=sessionmaker(bind=engine)
    monkeypatch.setattr(store,'SessionSesiones',factory)
    monkeypatch.setattr(panel_send_once,'SessionSesiones',factory)
    store.obtener_o_crear_sesion('5071')
    yield configured,current,sent
    engine.dispose()

def test_send_uses_current_pin_records_history_and_deduplicates(api):
    point,_,sent=api
    body={'mensaje':point['revision'],'request_id':'location-1'}
    for _ in range(2):
        result=asyncio.run(panel.enviar_ubicacion_desde_panel('5071',body,'alexander'))
        assert result['whatsapp_message_id']=='wamid-location'
    sent.assert_awaited_once_with('5071',point['ubicacion'])
    history=store.obtener_sesion_existente('5071').obtener_historial()
    assert len(history)==1 and history[0]['ubicacion']==point['ubicacion']
    assert history[0]['estado_entrega']=='accepted' and history[0]['operador']=='alexander'
    store.actualizar_estado_mensaje_whatsapp('wamid-location','delivered')
    assert store.obtener_sesion_existente('5071').obtener_historial()[0]['estado_entrega']=='delivered'

def test_rejects_other_owner_stale_preview_and_missing_id(api,monkeypatch):
    point,current,sent=api
    current.atencion_humana_por='teresa'
    with pytest.raises(HTTPException):
        asyncio.run(panel.enviar_ubicacion_desde_panel('5071',{'mensaje':point['revision']},'alexander'))
    current.atencion_humana_por='alexander'
    for body in ({'mensaje':'old','request_id':'stale'},{'mensaje':point['revision']}):
        with pytest.raises(HTTPException):
            asyncio.run(panel.enviar_ubicacion_desde_panel('5071',body,'alexander'))
    sent.assert_not_called()

def test_uncertain_send_is_not_repeated_or_recorded_as_success(api):
    point,_,sent=api
    sent.side_effect=httpx.ReadTimeout('timeout')
    body={'mensaje':point['revision'],'request_id':'uncertain'}
    for _ in range(2):
        with pytest.raises(HTTPException):
            asyncio.run(panel.enviar_ubicacion_desde_panel('5071',body,'alexander'))
    sent.assert_awaited_once()
    assert store.obtener_sesion_existente('5071').obtener_historial()==[]

def test_routes_require_authentication():
    app=FastAPI();app.include_router(panel.router)
    with TestClient(app) as client:
        assert client.get('/panel/ubicacion-local').status_code==401
        assert client.post('/panel/enviar-ubicacion/5071',json={}).status_code==401

def test_native_meta_payload_and_cost_registration(configured,monkeypatch):
    post=AsyncMock(return_value=httpx.Response(200,json={'messages':[{'id':'wamid-native'}]}))
    client=AsyncMock();client.post=post
    manager=AsyncMock();manager.__aenter__.return_value=client
    monkeypatch.setattr(whatsapp.httpx,'AsyncClient',Mock(return_value=manager))
    cost=Mock();monkeypatch.setattr(whatsapp,'record_whatsapp_response',cost)
    asyncio.run(whatsapp.enviar_ubicacion_whatsapp('5071',configured['ubicacion']))
    payload=post.call_args.kwargs['json']
    assert payload=={'messaging_product':'whatsapp','to':'5071','type':'location','location':configured['ubicacion']}
    assert cost.call_args.args[1:]==('5071','location')
