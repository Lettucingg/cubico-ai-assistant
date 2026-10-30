"""Real SQL and production paths; no language-model response is mocked for mailboxes."""
from unittest.mock import Mock
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.db.models import ClienteCBC, Agencia
from app.db import session_store
from app.services import staff_customers as customers, internal_assistant as service
from app.api import panel


@pytest.fixture
def records(monkeypatch):
    from app.services import cost_analytics
    monkeypatch.setattr(cost_analytics,'call_anthropic',Mock(side_effect=AssertionError('Mailbox tests must not call a model')))
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    ClienteCBC.__table__.create(engine);Agencia.__table__.create(engine)
    factory=sessionmaker(bind=engine)
    with factory() as db:
        db.add_all([
            ClienteCBC(codigo='CBC-0001',nombre='Alexander',apellido='Santa María',telefono='+507 6000-1111',activo=True,email='private@example.com',cedula='private-id',password_hash='private-password'),
            ClienteCBC(codigo='CBC-0108',nombre='Roxana',apellido='Esquivel',telefono='50760002222',activo=True),
            ClienteCBC(codigo='CBC-0003',nombre='Alexander',apellido='Rodríguez',activo=True),
            ClienteCBC(codigo='CBC-0004',nombre='Inactivo',apellido='Santamaría',activo=False),
            Agencia(codigo='AG1',nombre='Empresa Uno',telefono='50760003333',activo=True),
        ]);db.commit()
    monkeypatch.setattr(customers,'SessionLocal',factory)
    monkeypatch.setattr(customers.settings,'CUBICO_MIAMI_STREET','STREET CONFIGURADA')
    monkeypatch.setattr(customers.settings,'CUBICO_MIAMI_CITY_ZIP','Doral FL ZIP CONFIGURADO')
    monkeypatch.setattr(customers.settings,'CUBICO_MIAMI_PHONE','WAREHOUSE-PHONE')
    yield factory
    engine.dispose()


def test_exact_reported_question_solves_mailbox_without_model_chat_or_billing(records,monkeypatch):
    from app.ai import orchestrator
    monkeypatch.setattr(orchestrator,'call_anthropic',Mock(side_effect=AssertionError('No model for mailboxes')))
    for name in ('consultar_facturas_por_codigo','consultar_paquetes_por_codigo','consultar_ultimo_pago_por_codigo'):
        monkeypatch.setattr(service,name,Mock(side_effect=AssertionError('Mailbox needs no financial query')))
    update=Mock(side_effect=AssertionError('Do not verify or link a WhatsApp customer'))
    monkeypatch.setattr(session_store,'actualizar_sesion',update)
    result=service.query_general('sabes cual es la ubicacion me refiero a la del casillero de alexander santamaria')
    assert result['cliente']['codigo']=='CBC-0001'
    assert 'Alexander Santa María CBC-0001' in result['respuesta']
    assert 'CUBICO CBC-0001 UNIT2' in result['respuesta']
    assert 'CUBICO OCEAN CBC-0001 UNIT2' in result['respuesta']
    assert 'STREET CONFIGURADA' in result['respuesta'] and 'Juan Pablo' not in result['respuesta']
    assert result['telefono'] is None and result['enviado'] is False
    update.assert_not_called()


@pytest.mark.parametrize('question',[
 'Dame el casillero de Alexander Santamaría',
 '¿Cuál es el casillero de Alexander Santa María?',
 'ubicacion del casillero de alexander santamaria',
 'Dirección del casillero de ALEXANDER SANTAMARIA',
 'casillero de Alexander Santamaría por favor',
 'casillero de Alexander Santamaria porfa',
 'casillero de Alexander Santamaria?',
 'casillero de Alexander Santa María, por favor',
 'casillero CBC-0001',
 'casillero CBC0001',
 'casillero cbc_0001',
 'casillero CBC 0001',
 'casillero aéreo de Alexander Santamaría',
 'casillero de Alexander Santamaría por aire',
 'casillero marítimo de Alexander Santamaría',
 'casillero de Alexander Santamaría por mar',
 'Dirección de Miami de CBC-0001',
 'direccion en miami CBC-0001',
 'casillero de teléfono +507 6000-1111',
 'Casillero del cliente CBC-0001',
])
def test_twenty_customer_messages_use_real_query_and_configured_address(question,records):
    result=service.query_general(question,'borrador')
    assert result['cliente']['codigo']=='CBC-0001'
    assert result['datos']['direcciones']
    assert 'STREET CONFIGURADA' in result['borrador']
    assert not result['enviado']


def test_ambiguous_does_not_choose_first_and_selection_resumes_same_question(records):
    result=service.query_general('Dame el casillero de Alexander')
    assert result['alcance']=='busqueda_clientes' and len(result['clientes'])==2
    assert not result['borrador']
    chosen=service.query_general('Dame el casillero de Alexander','borrador','CBC-0003','cbc')
    assert chosen['cliente']['codigo']=='CBC-0003'
    assert 'CBC-0001' not in chosen['borrador']


def test_switching_reference_cannot_reuse_old_customer(records):
    result=service.query_general('Dame el casillero de Roxana Esquivel','borrador','CBC-0001','cbc')
    assert result['cliente']['codigo']=='CBC-0108'
    assert 'CBC-0001' not in result['borrador']


def test_inactive_missing_database_failure_and_no_sensitive_search_fields(records,monkeypatch):
    assert customers.search('Inactivo')['clientes']==[]
    assert customers.search('not-present')['clientes']==[]
    results=customers.search('Alexander')
    assert 'private-' not in str(results) and 'private@example' not in str(results)
    assert set(results['clientes'][0])=={'codigo','tipo','nombre','telefono_referencia'}
    with pytest.raises(ValueError):customers.search('%%')
    assert customers.search("Alexander%' OR 1=1 --")['clientes']==[]
    monkeypatch.setattr(customers,'SessionLocal',Mock(side_effect=RuntimeError('private-db')))
    with pytest.raises(RuntimeError):service.query_general('casillero CBC-0001')


def test_missing_warehouse_not_replaced_by_local_or_invented_phone(records,monkeypatch):
    monkeypatch.setattr(customers.settings,'CUBICO_MIAMI_PHONE','')
    result=service.query_general('Casillero aéreo CBC-0001','borrador')
    assert result['borrador']=='' and 'teléfono' in result['respuesta']
    assert 'Juan Pablo' not in result['respuesta']


def test_selected_account_queries_work_without_verifying_any_chat(records,monkeypatch):
    query=Mock(return_value={'respuesta':'Saldo total: $10.00','borrador':'Debes $10.00','privado':True,'consultado_en':'now'})
    monkeypatch.setattr(service,'query_chat',query)
    result=service.query_general('¿Cuánto debe?','borrador','CBC-0108','cbc')
    assert result['cliente']['codigo']=='CBC-0108' and '$10.00' in result['borrador']
    context=query.call_args.args[0]
    assert context.codigo_cliente_verificado=='CBC-0108' and context.obtener_historial()==[]
    with pytest.raises(ValueError):service.query_general('Saldo','consulta','CBC-0004','cbc')


def test_internal_search_auth_and_full_request_without_chat(records,monkeypatch):
    app=FastAPI();app.include_router(panel.router);client=TestClient(app)
    assert client.get('/panel/asistente/clientes?q=Alexander').status_code==401
    app.dependency_overrides[panel.verificar_credenciales_panel]=lambda:'alexander'
    result=client.get('/panel/asistente/clientes?q=Alexander')
    assert result.status_code==200 and len(result.json()['clientes'])==2
    assert client.get('/panel/asistente/clientes?q=x').status_code==422
    result=client.post('/panel/asistente',json={'pregunta':'Casillero aéreo','modo':'borrador','cliente_codigo':'CBC-0108','cliente_tipo':'cbc'})
    assert result.status_code==200 and 'CBC-0108' in result.json()['borrador']
    assert 'OCEAN' not in result.json()['borrador']
    with records() as db:
        assert db.scalar(select(func.count()).select_from(ClienteCBC))==4
