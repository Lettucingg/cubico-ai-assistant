"""Behavioral tests for incident persistence, isolated credentials and real MCP transport."""
import asyncio
import hashlib
import json
from datetime import datetime, timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.api import panel, staff_mcp
from app.services import incidents, ai_connections
from app.db import session_store


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    session_store.BaseSesiones.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    for module in (incidents, ai_connections, staff_mcp):
        monkeypatch.setattr(module, 'SessionSesiones', factory)
    monkeypatch.setattr(panel, 'USUARIOS_PANEL', {'alexander':'test', 'luis':'test'})
    return factory


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(panel.router)
    app.dependency_overrides[panel.verificar_credenciales_panel] = lambda:'alexander'
    return TestClient(app)


def new_ticket(**extra):
    return {'titulo':'No responde el botón', 'descripcion':'Abro chat y toco Alertas; no cambia.', 'esperado':'Abrir alertas', 'seccion':'chats', 'tipo':'problema', 'prioridad':'normal', 'contexto':'iPhone · 1.5.0', 'captura':None, **extra}


def test_incident_shared_history_reopen_and_stale_edit(db, client):
    d = client.post('/panel/incidencias', json=new_ticket()).json()
    assert d['codigo'] == 'INC-0001' and d['creador'] == 'alexander' and d['revision'] == 1
    patch = {'revision':1, 'estado':'en_revision', 'prioridad':'alta', 'responsable':'luis', 'nota':'Confirmado en Android'}
    d2 = client.patch('/panel/incidencias/1', json=patch).json()
    assert d2['revision'] == 2 and d2['historial'][-1]['nota'] == patch['nota']
    assert client.patch('/panel/incidencias/1', json=patch).status_code == 409
    for state in ('resuelta', 'pendiente'):
        d2 = client.patch('/panel/incidencias/1', json={**patch,'revision':d2['revision'],'estado':state}).json()
    assert len(d2['historial']) == 4
    assert client.get('/panel/incidencias?estado=resuelta').json()['incidencias'] == []
    listed = client.get('/panel/incidencias?estado=pendiente&seccion=chats').json()['incidencias']
    assert len(listed) == 1 and 'historial' not in listed[0] and 'captura' not in listed[0]
    assert client.get('/panel/incidencias/9999').status_code == 404
    assert client.patch('/panel/incidencias/1',json={**patch, 'revision':d2['revision'], 'responsable':'stranger'}).status_code == 400


def test_incident_auth_validation_and_images(db, client):
    assert client.post('/panel/incidencias',json=new_ticket(titulo='   ')).status_code == 400
    assert client.post('/panel/incidencias',json=new_ticket(captura='data:image/svg+xml;base64,abc')).status_code == 400
    assert client.post('/panel/incidencias',json=new_ticket(seccion='secret')).status_code == 400
    assert client.get('/panel/incidencias?estado=oops').status_code == 400
    app=FastAPI();app.include_router(panel.router)
    c=TestClient(app)
    assert c.get('/panel/incidencias').status_code == 401
    assert c.post('/panel/conexiones-ia',json={'nombre':'test','permisos':['incidencias']}).status_code == 401


def test_credentials_isolated_hashed_expire_revoke_rate_limit(db, client):
    a = ai_connections.issue('alexander','Mi Claude',['incidencias'])
    b = ai_connections.issue('luis','Claude de Luis',['conversaciones'])
    assert a['token'] != b['token'] and 'token' not in str(ai_connections.listing('alexander'))
    assert ai_connections.listing('alexander')[0]['id'] == a['id']
    with db() as s:
        row=s.get(session_store.ConexionIAPanel,a['id'])
        assert row.token_hash == hashlib.sha256(a['token'].encode()).hexdigest()
        assert a['token'] not in str(row.__dict__)
    assert client.delete('/panel/conexiones-ia/'+b['id']).status_code == 404
    actor=ai_connections.authenticate(a['token'],panel.USUARIOS_PANEL)
    for _ in range(60): assert ai_connections.touch(actor)
    assert not ai_connections.touch(actor)
    assert ai_connections.authenticate(a['token'],{'luis':'test'}) is None
    ai_connections.revoke('alexander',a['id'])
    assert ai_connections.authenticate(a['token'],panel.USUARIOS_PANEL) is None
    assert ai_connections.authenticate(b['token'],panel.USUARIOS_PANEL)['usuario'] == 'luis'
    with db() as s:
        row=s.get(session_store.ConexionIAPanel,b['id']);row.vence_en=datetime.utcnow()-timedelta(seconds=1);s.commit()
    assert ai_connections.authenticate(b['token'],panel.USUARIOS_PANEL) is None
    assert client.post('/panel/conexiones-ia',json={'nombre':'Test','permisos':['cuentas']}).status_code == 400
    issued=client.post('/panel/conexiones-ia',json={'nombre':'Test','permisos':['incidencias']})
    assert issued.status_code == 201 and issued.headers['cache-control']=='no-store'


def test_real_mcp_initialize_tools_and_permission_denial(db, monkeypatch):
    """Exercise SDK transport, ASGI context propagation and an actual tools/call."""
    from contextlib import asynccontextmanager
    @asynccontextmanager
    async def life(app):
        async with staff_mcp.mcp.session_manager.run():
            yield
    app=FastAPI(lifespan=life); app.mount('/mcp', staff_mcp.mcp_app)
    a=ai_connections.issue('alexander','A',['incidencias'])
    b=ai_connections.issue('luis','B',['conversaciones'])
    incidents.create(new_ticket(captura='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jBScAAAAASUVORK5CYII='), 'alexander')
    headers={'Accept':'application/json, text/event-stream', 'Authorization':'Bearer '+a['token']}
    def rpc(c, method, params=None, hdr=None):
        return c.post('/mcp/',headers=hdr or headers,json={'jsonrpc':'2.0','id':1,'method':method,'params':params or {}})
    with TestClient(app) as c:
        assert c.post('/mcp/',json={}).status_code==401
        assert rpc(c,'initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'qa','version':'1'}}).status_code == 200
        result=rpc(c,'tools/list').json()['result']
        assert {t['name'] for t in result['tools']} == {'resumen_operativo','listar_pendientes','listar_chats','buscar_chats','leer_conversacion','consultar_cuenta','consultar_tracking','revisar_incidencias','ver_captura_incidencia','consultar_operacion'}
        assert all(t['annotations']['readOnlyHint'] for t in result['tools'])
        out=rpc(c,'tools/call',{'name':'revisar_incidencias','arguments':{}})
        assert out.status_code == 200 and 'INC-0001' in out.text and out.headers['cache-control']=='no-store'
        capture=rpc(c,'tools/call',{'name':'ver_captura_incidencia','arguments':{'incidencia_id':1}}).json()['result']
        assert capture['content'][0]['type']=='image' and capture['content'][0]['mimeType']=='image/png'
        denied=rpc(c,'tools/call',{'name':'buscar_chats','arguments':{'consulta':'5071'}}).json()['result']
        assert denied['isError'] and 'permiso' in str(denied)
        hb={**headers,'Authorization':'Bearer '+b['token']}
        denied=rpc(c,'tools/call',{'name':'revisar_incidencias','arguments':{}},hb).json()['result']
        assert denied['isError'] and 'INC-0001' not in str(denied)
        assert rpc(c,'tools/list',hdr={**headers,'Origin':'https://evil.invalid'}).status_code==403
        unknown=rpc(c,'tools/call',{'name':'enviar_whatsapp','arguments':{}}).json()['result']
        assert unknown['isError']
        ai_connections.revoke('alexander',a['id'])
        assert rpc(c,'tools/list').status_code==401


def test_account_requires_verified_identity_and_never_uses_ai(db,monkeypatch):
    from types import SimpleNamespace
    from app.services import internal_assistant as service
    monkeypatch.setattr(staff_mcp,'require',lambda *args:None)
    row=SimpleNamespace(codigo_cliente_verificado=None,tipo_cliente_verificado=None)
    monkeypatch.setattr(staff_mcp,'session_for',lambda phone:row)
    with pytest.raises(ValueError,match='verifica'):staff_mcp.consultar_cuenta('5071234567')
    row.codigo_cliente_verificado='CBC-0001';row.tipo_cliente_verificado='cbc'
    monkeypatch.setattr(service,'consultar_facturas_por_codigo',lambda code:{'encontrado':True,'codigo_cliente':'CBC-9999','saldo_pendiente_total':0})
    monkeypatch.setattr(service,'consultar_paquetes_por_codigo',lambda code:(_ for _ in ()).throw(RuntimeError('secret')))
    monkeypatch.setattr(service,'consultar_ultimo_pago_por_codigo',lambda code:{'encontrado':True,'codigo_cliente':code})
    out=staff_mcp.consultar_cuenta('5071234567')
    assert not out['datos']['facturas']['disponible'] and not out['datos']['paquetes']['disponible']
    assert 'secret' not in str(out)
