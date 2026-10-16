import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient
from app.services import internal_assistant as service, panel_send_once
from app.db.session_store import EnvioPanelUnico
from app.api import panel


def session(code='CBC-0001'):
    return SimpleNamespace(telefono='5071', codigo_cliente_verificado=code, tipo_cliente_verificado='cbc',
                           atencion_humana_directa=False, atencion_humana_por=None,
                           obtener_historial=lambda:[{'role':'user','content':'El total porfa'},
                                                      {'role':'assistant','content':'Notificación FAC-2 total USD 5.00'}])


@pytest.fixture
def sources(monkeypatch):
    billing = {'encontrado':True,'codigo_cliente':'CBC-0001','tipo_cliente':'cbc','cliente':'Cliente',
               'saldo_pendiente_total':10,'cantidad_facturas':3,
               'facturas':[{'codigo':'FAC-1','total':8,'saldo_pendiente':5,'estado':'parcial'},
                           {'codigo':'FAC-2','total':5,'saldo_pendiente':5,'estado':'pendiente'},
                           {'codigo':'FAC-3','total':7,'saldo_pendiente':0,'estado':'pagado'}]}
    packages = {'encontrado':True,'codigo_cliente':'CBC-0001','tipo_cliente':'cbc','cantidad_paquetes':1,
                'paquetes':[{'tracking':'ABC123','estado_cargo':'en_miami','estado_pago':'pendiente'}]}
    monkeypatch.setattr(service,'consultar_facturas_por_codigo',Mock(return_value=billing))
    monkeypatch.setattr(service,'consultar_paquetes_por_codigo',Mock(return_value=packages))
    monkeypatch.setattr(service,'consultar_ultimo_pago_por_codigo',Mock(return_value={
        'encontrado':True,'codigo_cliente':'CBC-0001','ultimo_pago':None}))
    return billing, packages


def test_sum_is_current_balance_not_notification_and_no_side_effects(sources):
    result = service.query_chat(session(), '¿Cuánto debe?', 'borrador')
    assert '$10.00' in result['respuesta'] and '$10.00' in result['borrador']
    assert 'FAC-1 ($5.00)' in result['borrador'] and 'FAC-3' not in result['borrador']
    assert result['privado'] is True
    service.consultar_facturas_por_codigo.assert_called_once_with('CBC-0001')
    assert service.query_chat(session(),'Saldo actual')['borrador'] == ''


def test_unverified_or_other_customer_cannot_query_sources(sources):
    with pytest.raises(service.UnlinkedCustomer):
        service.query_chat(session(None), 'Saldo')
    with pytest.raises(service.UnlinkedCustomer):
        service.query_chat(session(), 'Consulta el saldo de CBC-0099')
    service.consultar_facturas_por_codigo.assert_not_called()


def test_failure_not_zero_and_wrong_identity_not_used(sources,monkeypatch):
    service.consultar_facturas_por_codigo.side_effect=RuntimeError('secret database address')
    result=service.query_chat(session(),'Saldo','borrador')
    assert '$0.00' not in result['borrador'] and 'secret' not in str(result)
    service.consultar_facturas_por_codigo.side_effect=None
    service.consultar_facturas_por_codigo.return_value={**sources[0],'codigo_cliente':'CBC-0099'}
    assert not service.query_chat(session(),'Saldo')['datos']['facturas']['disponible']
    service.consultar_facturas_por_codigo.return_value={**sources[0],'tipo_cliente':'agencia'}
    assert not service.query_chat(session(),'Saldo')['datos']['facturas']['disponible']


def test_last_payment_does_not_invent_date_and_generic_reply_uses_customer_question(sources):
    result=service.query_chat(session(),'¿Cuándo fue el último pago?','consulta')
    assert 'No hay una fecha' in result['respuesta']
    result=service.query_chat(session(),'Qué le contesto al último mensaje','borrador')
    assert '$10.00' in result['borrador']


def test_llm_is_metered_has_no_tools_and_no_operator_name(sources,monkeypatch):
    from app.ai import orchestrator
    from app.services import cost_analytics
    client=Mock();client.with_options.return_value=client
    monkeypatch.setattr(orchestrator,'cliente_claude',client)
    call=Mock(return_value=SimpleNamespace(content=[SimpleNamespace(type='text',text='{"respuesta":"Falta confirmar el punto vigente.","borrador":"El equipo confirmará el punto exacto."}')]))
    monkeypatch.setattr(cost_analytics,'call_anthropic',call)
    monkeypatch.setattr(service,'active_context',lambda *_:[])
    monkeypatch.setattr(service,'verified_location',lambda:None)
    result=service.query_chat(session(),'¿Dónde queda el local?','borrador')
    assert result['borrador']=='El equipo confirmará el punto exacto.'
    assert call.call_args.kwargs['task']=='asistente_interno'
    assert call.call_args.kwargs['phone']=='5071'
    assert 'tools' not in call.call_args.kwargs
    assert 'punto_retiro_verificado' in call.call_args.kwargs['messages'][0]['content']
    call.return_value=SimpleNamespace(content=[SimpleNamespace(type='text',text='not json')])
    with pytest.raises(ValueError):
        service.query_chat(session(),'Otra consulta')


def test_truncation_preserves_complete_total(sources):
    sources[0]['facturas'] *= 30
    result=service.query_chat(session(),'Saldo')
    assert result['datos']['facturas']['detalle_limitado']
    assert len(result['datos']['facturas']['facturas'])==60
    assert result['datos']['facturas']['saldo_pendiente_total']==10


@pytest.fixture
def api(monkeypatch,tmp_path):
    current=session()
    monkeypatch.setattr(panel,'obtener_sesion_existente',lambda _:current)
    sent=AsyncMock(return_value=SimpleNamespace(is_success=True))
    history=Mock()
    monkeypatch.setattr(panel,'enviar_respuesta_natural',sent)
    monkeypatch.setattr(panel,'extraer_id_mensaje_meta',lambda _:'wamid-test')
    monkeypatch.setattr(panel,'agregar_al_historial',history)
    monkeypatch.setattr(panel,'redactar_respuesta_de_asesor',Mock(side_effect=AssertionError('Must not rewrite reviewed text')))
    engine=create_engine('sqlite:///'+str(tmp_path/'send.db'))
    EnvioPanelUnico.__table__.create(engine)
    monkeypatch.setattr(panel_send_once,'SessionSesiones',sessionmaker(bind=engine))
    yield current,sent,history
    engine.dispose()


def test_reviewed_message_verbatim_and_retry_does_not_send_twice(api):
    _, sent, history=api
    body={'mensaje':'Tu saldo es $10.00.','codigo_cliente':'CBC-0001','request_id':'reviewed-1'}
    for _ in range(2):
        assert asyncio.run(panel.enviar_respuesta_revisada('5071',body,'alexander'))['status']=='enviado'
    sent.assert_awaited_once()
    assert sent.call_args.args==('5071','Tu saldo es $10.00.')
    assert sent.call_args.kwargs['dividir'] is False
    assert history.call_args.kwargs['modo_envio']=='revisado_bruno'


def test_reviewed_send_checks_current_identity_and_owner(api):
    current,sent,_=api
    with pytest.raises(HTTPException) as exc:
        asyncio.run(panel.enviar_respuesta_revisada('5071',{'mensaje':'Hola','codigo_cliente':'CBC-2'},'alexander'))
    assert exc.value.status_code==409
    current.atencion_humana_directa=True;current.atencion_humana_por='teresa'
    with pytest.raises(HTTPException) as exc:
        asyncio.run(panel.enviar_respuesta_revisada('5071',{'mensaje':'Hola','codigo_cliente':'CBC-0001'},'alexander'))
    assert exc.value.status_code==409
    sent.assert_not_called()


def test_private_query_does_not_send_and_rejects_identity_change(api,sources,monkeypatch):
    current,sent,history=api
    result=asyncio.run(panel.consultar_bruno_panel('5071',panel.ConsultaBrunoPayload(pregunta='Saldo'),'alexander'))
    assert result['privado']
    sent.assert_not_called();history.assert_not_called()
    def changed(*_):
        current.codigo_cliente_verificado='CBC-0099'
        return result
    monkeypatch.setattr(service,'query_chat',changed)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(panel.consultar_bruno_panel('5071',panel.ConsultaBrunoPayload(pregunta='Saldo'),'alexander'))
    assert exc.value.status_code==409


def test_routes_require_authentication_and_validate_payload():
    app=FastAPI();app.include_router(panel.router)
    with TestClient(app) as client:
        assert client.post('/panel/asistente/5071',json={'pregunta':'Saldo'}).status_code==401
        assert client.post('/panel/responder-revisado/5071',json={'mensaje':'Hola'}).status_code==401
    with pytest.raises(ValueError):
        panel.ConsultaBrunoPayload(pregunta=' ')

@pytest.mark.parametrize('kind', ['cbc','agencia'])
def test_real_database_balance_includes_other_invoice_partial_and_cancelled_payments(tmp_path,monkeypatch,kind):
    from app.db.database import Base
    from app.db.models import ClienteCBC, Agencia, Factura, Pago
    from app.tools import clientes, facturas, paquetes
    engine=create_engine('sqlite:///'+str(tmp_path/'billing.db'))
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine)
    for module in (clientes,facturas,paquetes):
        monkeypatch.setattr(module,'SessionLocal',factory)
    code='CBC-0001' if kind=='cbc' else 'SFE'
    with factory() as db:
        customer=ClienteCBC(codigo=code,nombre='Persona',activo=True) if kind=='cbc' else Agencia(codigo=code,nombre='Agencia',activo=True)
        db.add(customer);db.flush()
        owner={'cliente_cbc_id':customer.id} if kind=='cbc' else {'agencia_id':customer.id}
        invoice=Factura(codigo='FAC-1',total=8,estado='parcial',tipo_cliente=kind,**owner)
        db.add(invoice);db.flush()
        db.add_all([Pago(factura_id=invoice.id,monto=3,anulado=False,metodo='yappy',tipo_pago='parcial',tipo_cliente=kind,**owner),
                    Pago(factura_id=invoice.id,monto=100,anulado=True,metodo='yappy',tipo_pago='parcial',tipo_cliente=kind,**owner),
                    Factura(codigo='FAC-2',total=5,estado='pendiente',tipo_cliente=kind,**owner),
                    Factura(codigo='FAC-3',total=9,estado='pagado',tipo_cliente=kind,**owner)])
        db.commit()
    current=session(code);current.tipo_cliente_verificado=kind
    result=service.query_chat(current,'¿Cuánto debe este cliente?','borrador')
    assert result['datos']['facturas']['saldo_pendiente_total']==10
    assert '$10.00' in result['borrador'] and 'FAC-3' not in result['borrador']
    engine.dispose()
