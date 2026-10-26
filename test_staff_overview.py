"""Behavioral coverage of operator queues, pagination, scope and MCP transport."""
import json
from datetime import datetime, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import session_store as models
from app.services import staff_overview as service, ai_connections
from app.api import staff_mcp, panel


@pytest.fixture
def db(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    models.BaseSesiones.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    for module in (staff_mcp,ai_connections):monkeypatch.setattr(module,'SessionSesiones',factory)
    monkeypatch.setattr(panel,'USUARIOS_PANEL',{'alexander':'test','luis':'test'})
    return factory


def seed(db):
    now=datetime.utcnow()
    with db() as s:
        s.add_all([
            models.Sesion(telefono='50760000001',necesita_atencion_humana=True,motivo_escalamiento='Consulta marítima',actualizado_en=now,historial_json=json.dumps([{'role':'user','content':'¿Qué incluye?'}])),
            models.Sesion(telefono='50760000002',aviso_retiro_pendiente=True,actualizado_en=now-timedelta(days=1)),
            models.Sesion(telefono='50760000003',solicitud_domicilio_pendiente=True,entregado=True),
            models.Sesion(telefono='50760000004',pago_reportado=True,pago_confirmado=False,entregado=True,codigo_cliente_verificado='CBC-0004',monto_pago_reportado=25,comprobante_media_id='private-id'),
            models.Sesion(telefono='50760000005',aviso_retiro_pendiente=True,entregado=True),
            models.OportunidadComercial(telefono='50760000001',estado='nueva',empresa='Librería',necesidad='Cotización aérea'),
            models.OportunidadComercial(telefono='50760000002',estado='propuesta_enviada'),
            models.OportunidadComercial(telefono='50760000003',estado='ganada'),
            models.OportunidadComercial(telefono='50760000004',estado='no_concretada')]);s.commit()


def test_actual_queues_pagination_and_no_writes(db):
    seed(db)
    with db() as s:
        expected={'atencion':1,'retiros':1,'domicilios':0,'comprobantes':1,'propuestas':2,'chats_registrados':5}
        assert service.summary(s)['conteos']==expected
        # Closed delivery must not hide an unconfirmed payment.
        payments=service.listing(s,'comprobantes');assert payments['total']==1
        item=payments['resultados'][0]
        assert item['pago_por_comprobar'] and item['tiene_comprobante']
        assert 'private-id' not in str(payments) and 'monto_reportado_no_validado' not in item
        assert service.listing(s,'comprobantes',accounts=True)['resultados'][0]['monto_reportado_no_validado']==25
        first=service.listing(s,'propuestas',limit=1)
        assert first['total']==2 and first['siguiente_desplazamiento']==1
        second=service.listing(s,'propuestas',limit=1,offset=1)
        assert first['resultados'][0]['id']!=second['resultados'][0]['id'] and second['siguiente_desplazamiento'] is None
        assert service.listing(s,'chats',limit=2)['total']==5
        assert service.listing(s,'atencion')['resultados'][0]['ultimo_mensaje_cliente']['texto']=='¿Qué incluye?'
        assert s.query(models.Sesion).filter_by(entregado=True).count()==3
        assert s.query(models.OportunidadComercial).count()==4


def test_message_context_does_not_treat_notifications_or_failed_sends_as_reply(db):
    seed(db)
    with db() as s:
        row=s.query(models.Sesion).filter_by(telefono='50760000001').one()
        history=[{'role':'user','content':'Quiero retirar'},
                 {'role':'assistant','content':'[Notificación enviada: carga disponible]','estado_entrega':'delivered'},
                 {'role':'humano','content':'Ven hoy','estado_entrega':'failed'}]
        row.historial_json=json.dumps(history);s.commit()
        result=service.chat(row)
        assert result['ultimo_cliente_sin_respuesta_registrada'] and result['ultima_respuesta']['entrega']=='failed'
        history.append({'role':'humano','content':'[Estado de envío: sent] Voy a revisar','estado_entrega':'sent'})
        row.historial_json=json.dumps(history)
        assert not service.chat(row)['ultimo_cliente_sin_respuesta_registrada']
        assert service.chat(row)['ultima_respuesta']['texto']=='Voy a revisar'
        row.historial_json='not json'
        assert not service.chat(row)['historial_disponible']
        assert service.chat(row)['ultimo_cliente_sin_respuesta_registrada'] is None


def test_validation_and_outages_never_become_empty_queues(db,monkeypatch):
    with db() as s:
        for args in [('inventado',20,0),('chats',100,0),('retiros',10,-1)]:
            with pytest.raises(ValueError):service.listing(s,*args)
    def unavailable():raise OperationalError('SELECT secret_connection','private',Exception('offline'))
    monkeypatch.setattr(staff_mcp,'SessionSesiones',unavailable)
    with pytest.raises(ValueError,match='no lo interpretes como cero') as error:staff_mcp._read_queue()
    assert 'secret_connection' not in str(error.value)


def test_real_mcp_tools_permission_revocation_and_read_only(db):
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings
    seed(db)
    server=FastMCP('qa',stateless_http=True,json_response=True,streamable_http_path='/',transport_security=TransportSecuritySettings(allowed_hosts=['testserver']))
    for function in (staff_mcp.resumen_operativo,staff_mcp.listar_pendientes,staff_mcp.listar_chats):
        server.add_tool(function,annotations=staff_mcp.READ_ONLY)
    @asynccontextmanager
    async def life(app):
        async with server.session_manager.run():yield
    app=FastAPI(lifespan=life);app.mount('/mcp',staff_mcp.PersonalConnectionAuth(server.streamable_http_app()))
    keys={name:ai_connections.issue('alexander',name,scopes) for name,scopes in [('reports',['incidencias']),('chats',['conversaciones']),('accounts',['conversaciones','cuentas'])]}
    with TestClient(app) as c:
        def rpc(key,method,params):
            return c.post('/mcp/',headers={'Authorization':'Bearer '+keys[key]['token'],'Accept':'application/json, text/event-stream'},json={'jsonrpc':'2.0','id':1,'method':method,'params':params})
        listing=rpc('chats','tools/list',{}).json()['result']['tools']
        assert all(t['annotations']['readOnlyHint'] for t in listing)
        denied=rpc('reports','tools/call',{'name':'resumen_operativo','arguments':{}}).json()['result']
        assert denied['isError'] and 'Librería' not in str(denied)
        result=rpc('chats','tools/call',{'name':'resumen_operativo','arguments':{}})
        assert result.status_code==200 and 'chats_registrados' in result.text and 'isError":true' not in result.text
        args={'name':'listar_pendientes','arguments':{'tipo':'comprobantes'}}
        assert 'monto_reportado_no_validado' not in rpc('chats','tools/call',args).text
        assert 'monto_reportado_no_validado' in rpc('accounts','tools/call',args).text
        assert '50760000001' in rpc('chats','tools/call',{'name':'listar_chats','arguments':{}}).text
        ai_connections.revoke('alexander',keys['chats']['id'])
        assert rpc('chats','tools/list',{}).status_code==401
