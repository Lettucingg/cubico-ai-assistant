import asyncio
from datetime import datetime,timedelta,timezone
from unittest.mock import AsyncMock,Mock
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.services import scheduled_template_test as s

NOW=datetime(2026,11,5,14)
REAL_ASYNC_CLIENT=httpx.AsyncClient
FETCH_TEMPLATE=s.fetch_template
TEMPLATE={'name':'cuenta_test','language':'es','status':'APPROVED','category':'UTILITY',
          'components':[{'type':'BODY','text':'Hola {{1}}, tu código es {{2}}. Es una prueba.'}]}


@pytest.fixture(autouse=True)
def setup(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'tests.db'))
    s.TestSend.__table__.create(engine)
    monkeypatch.setattr(s,'SessionSesiones',sessionmaker(bind=engine))
    monkeypatch.setattr(s,'now_utc',lambda:NOW)
    monkeypatch.setattr(s.settings,'CUBICO_TEST_RECIPIENTS_JSON','["50760000000"]')
    monkeypatch.setattr(s,'fetch_template',AsyncMock(return_value=TEMPLATE.copy()))
    # Every HTTP request is intercepted, including requests unexpectedly introduced.
    real_client=REAL_ASYNC_CLIENT
    posts=[]
    def handler(request):
        assert request.method=='POST'
        posts.append(request)
        return httpx.Response(200,json={'messages':[{'id':'wamid-test'}]})
    transport=httpx.MockTransport(handler)
    monkeypatch.setattr(s.httpx,'AsyncClient',lambda **kwargs:real_client(transport=transport,**kwargs))
    from app.services import cost_analytics
    monkeypatch.setattr(cost_analytics,'record_whatsapp_response',Mock())
    yield posts
    engine.dispose()


def schedule(**updates):
    kwargs=dict(key='test-1',recipient='50760000000',name='cuenta_test',language='es',values=['Equipo','TEST-0000'],
                when=(NOW+timedelta(minutes=5)).replace(tzinfo=timezone.utc))
    kwargs.update(updates)
    return asyncio.run(s.schedule(**kwargs))


def make_due(monkeypatch):monkeypatch.setattr(s,'now_utc',lambda:NOW+timedelta(minutes=6))


def test_only_team_recipients_and_timezone_allowed(setup):
    with pytest.raises(ValueError,match='lista autorizada'):schedule(recipient='50761111111')
    with pytest.raises(ValueError,match='zona horaria'):schedule(when=NOW+timedelta(hours=1))
    assert setup==[] and s.list_tests()==[]


@pytest.mark.parametrize('status',['PENDING','REJECTED','PAUSED','DISABLED'])
def test_nonapproved_template_cannot_be_scheduled(status,monkeypatch,setup):
    monkeypatch.setattr(s,'fetch_template',AsyncMock(return_value={**TEMPLATE,'status':status}))
    with pytest.raises(ValueError,match='no está aprobada'):schedule()
    assert setup==[] and s.list_tests()==[]


def test_idempotent_registration_no_duplicate_after_scheduler_restart(monkeypatch,setup):
    result=schedule();assert 'TEST-0000' in result['vista_previa']
    assert schedule()['estado']=='programada' and len(s.list_tests())==1
    with pytest.raises(ValueError,match='otros datos'):schedule(values=['Otro','TEST-0001'])
    make_due(monkeypatch)
    asyncio.run(s.run_due());asyncio.run(s.run_due())
    assert len(setup)==1
    item=s.list_tests()[0]
    assert item['estado']=='aceptada' and item['wamid']=='wamid-test'
    assert item['telefono']=='…0000' and 'no confirma entrega' in item['detalle']


def test_two_workers_claim_only_one_send(monkeypatch,setup):
    schedule();make_due(monkeypatch)
    async def workers():await asyncio.gather(s.run_due(),s.run_due())
    asyncio.run(workers())
    assert len(setup)==1 and s.list_tests()[0]['estado']=='aceptada'


def test_meta_lookup_exact_name_language_and_account(monkeypatch):
    monkeypatch.setattr(s.settings,'WHATSAPP_BUSINESS_ACCOUNT_ID','123456')
    def handler(request):
        assert request.method=='GET' and request.url.path=='/v21.0/123456/message_templates'
        assert request.url.params['name']=='cuenta_test'
        return httpx.Response(200,json={'data':[{**TEMPLATE,'language':'en'},TEMPLATE]})
    monkeypatch.setattr(s.httpx,'AsyncClient',lambda **kw:REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler),**kw))
    assert asyncio.run(FETCH_TEMPLATE('cuenta_test','es'))['language']=='es'
    with pytest.raises(ValueError,match='No se encontró'):asyncio.run(FETCH_TEMPLATE('cuenta_test','fr'))


@pytest.mark.parametrize('change',['recipient','status','content'])
def test_runtime_rechecks_block_changed_conditions(change,monkeypatch,setup):
    schedule();make_due(monkeypatch)
    if change=='recipient':monkeypatch.setattr(s.settings,'CUBICO_TEST_RECIPIENTS_JSON','[]')
    if change=='status':monkeypatch.setattr(s,'fetch_template',AsyncMock(return_value={**TEMPLATE,'status':'REJECTED'}))
    if change=='content':monkeypatch.setattr(s,'fetch_template',AsyncMock(return_value={**TEMPLATE,'components':[{'type':'BODY','text':'Otro {{1}} y {{2}}.'}]}))
    asyncio.run(s.run_due());assert s.list_tests()[0]['estado']=='bloqueada' and setup==[]


def test_cancel_and_expired_jobs_never_send(monkeypatch,setup):
    schedule();s.cancel('test-1');make_due(monkeypatch);asyncio.run(s.run_due())
    assert s.list_tests()[0]['estado']=='cancelada' and setup==[]
    monkeypatch.setattr(s,'now_utc',lambda:NOW)
    schedule(key='test-2');monkeypatch.setattr(s,'now_utc',lambda:NOW+timedelta(hours=2))
    asyncio.run(s.run_due());assert any(r['estado']=='vencida' for r in s.list_tests()) and setup==[]


def test_timeout_is_uncertain_and_not_retried(monkeypatch,setup):
    schedule();make_due(monkeypatch)
    attempts=[]
    def timeout(request):attempts.append(request);raise httpx.ReadTimeout('unknown outcome',request=request)
    monkeypatch.setattr(s.httpx,'AsyncClient',lambda **kw:REAL_ASYNC_CLIENT(transport=httpx.MockTransport(timeout),**kw))
    asyncio.run(s.run_due());asyncio.run(s.run_due())
    assert s.list_tests()[0]['estado']=='incierta' and len(attempts)==1


@pytest.mark.parametrize('values',[[],['Nombre'],['Nombre','Código','Extra'],['Nombre',''],{'1':'Nombre'}])
def test_missing_or_mismatched_variables_rejected(values,setup):
    with pytest.raises(ValueError):schedule(values=values)
    assert s.list_tests()==[] and setup==[]
