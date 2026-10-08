from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace as NS
import json
import pytest
from pydantic import ValidationError
from app.services import cost_analytics as c
from app.api.panel import GastoBot

@pytest.fixture(autouse=True)
def clean():
    with c.SessionSesiones() as db:
        db.query(c.CostEvent).delete()
        db.query(c.ConfirmedExpense).delete()
        db.query(c.UsoIA).delete()
        db.commit()
    yield


def response(**usage):
    return NS(id='req-1', model='claude-sonnet-5', usage=NS(**usage))


def test_cache_price_snapshot_and_legacy_not_double_counted():
    c.record_anthropic(response(input_tokens=1000, output_tokens=2000, cache_read_input_tokens=3000,
        cache_creation_input_tokens=5000, cache_creation=NS(ephemeral_5m_input_tokens=4000,ephemeral_1h_input_tokens=1000)), '5071')
    c.record_anthropic(response(input_tokens=1000), '5071') # Duplicate request, including legacy insert rolled back.
    with c.SessionSesiones() as db:
        e=db.query(c.CostEvent).one()
        assert e.cost == Decimal('.0366')
        assert json.loads(e.pricing_json)['usd_per_million']['input']=='2'
        assert db.query(c.UsoIA).count()==1
        assert db.query(c.UsoIA).one().input_tokens==9000
    today=c.datetime.now(c.PANAMA).date()
    data=c.analytics(today,today)
    assert data['totales']['eventos']==1
    assert data['totales']['tokens']==11000
    assert data['totales']['costo_usd']==pytest.approx(.0366)
    assert data['historicos_sin_desglose']==0


def test_unknown_model_and_missing_usage_never_free():
    c.record_anthropic(NS(id='unknown',model='future-model',usage=NS(input_tokens=5,output_tokens=2)), '5071')
    c.record_anthropic(NS(id='missing',model='claude-sonnet-5',usage=None), '5071')
    today=c.datetime.now(c.PANAMA).date()
    assert c.analytics(today,today)['totales']['sin_precio']==2
    with c.SessionSesiones() as db: assert db.query(c.UsoIA).count()==0


def event(stamp, **kw):
    c.record_event(provider=kw.pop('provider','anthropic'), task=kw.pop('task','respuesta_automatica'), created_at=datetime.fromisoformat(stamp), **kw)


def test_panama_midnight_leap_year_zero_buckets_and_comparison():
    event('2024-02-29T04:59:59',cost=Decimal('1'),phone='a') # Feb28 Panama
    event('2024-02-29T05:00:00',cost=Decimal('2'),phone='a')
    event('2024-03-01T04:59:59',cost=Decimal('3'),phone='a')
    event('2024-03-01T05:00:00',cost=Decimal('99'),phone='a') # excluded
    data=c.analytics(date(2024,2,29),date(2024,2,29))
    assert data['totales']['costo_usd']==5
    assert data['anterior']['costo_usd']==1
    assert data['anterior']['desde']=='2024-02-28'
    assert data['picos']['dia']['fecha']=='2024-02-29'
    assert data['horas'][0]==1 and data['horas'][23]==1
    assert data['dias_semana'][3]==2
    data=c.analytics(date(2024,2,27),date(2024,2,29))
    assert len(data['serie'])==3 and data['serie'][0]['eventos']==0
    assert c.analytics(date(2024,2,1),date(2024,3,1),'mes')['serie'][0]['eventos']==3
    assert len(c.analytics(date(2023,1,1),date(2025,1,1),'ano')['serie'])==3


def test_historical_values_preserved_filters_and_unassigned_average():
    with c.SessionSesiones() as db:
        db.add(c.UsoIA(telefono='old',modelo='old-model',input_tokens=10,output_tokens=5,costo_usd=.4,creado_en=datetime(2026,10,8,10)))
        db.commit()
    event('2026-10-08T10:00:00',provider='openai',task='transcripcion_audio',cost=Decimal('.006'),audio_seconds=60,phone='new')
    event('2026-10-08T10:00:00',cost=Decimal('100'),phone='')
    data=c.analytics(date(2026,10,8),date(2026,10,8))
    assert data['historicos_sin_desglose']==1
    assert data['totales']['promedio_por_chat']==pytest.approx(.203)
    filtered=c.analytics(date(2026,10,8),date(2026,10,8),provider='openai')
    assert filtered['totales']['segundos_audio']==60
    assert filtered['totales']['costo_usd']==.006
    assert c.analytics(date(2026,10,8),date(2026,10,8),task='historico_sin_desglose')['totales']['costo_usd']==.4


def test_all_meta_receipts_dedup_billable_unknown_and_no_status_regression():
    def webhook(statuses): return {'entry':[{'changes':[{'value':{'statuses':statuses}}]}]}
    c.record_whatsapp_receipts(webhook([{'id':'m1','status':'read','recipient_id':'507','pricing':{'billable':False}}, {'id':'m2','status':'delivered','pricing':{'billable':True,'category':'utility'}}]))
    c.record_whatsapp_receipts(webhook([{'id':'m1','status':'sent'}]))
    c.record_whatsapp_response(NS(is_success=True,json=lambda:{'messages':[{'id':'m1'}]}),'507','text')
    with c.SessionSesiones() as db:
        rows={e.external_key:e for e in db.query(c.CostEvent)}
        assert len(rows)==2
        assert rows['meta:m1'].status=='read' and rows['meta:m1'].cost==0
        assert rows['meta:m1'].task=='mensaje_text'
        assert rows['meta:m2'].cost is None


def test_audio_tracking_known_missing_and_failed(monkeypatch):
    from app.tools import transcripcion as t
    for duration, expected in [(60,Decimal('.006')), (None,None)]:
        monkeypatch.setattr(t.cliente_openai.audio.transcriptions,'create',lambda **kw:NS(text='hola',duration=duration))
        assert t.transcribir_audio(b'audio','507')=='hola'
        with c.SessionSesiones() as db:
            row=db.query(c.CostEvent).order_by(c.CostEvent.id.desc()).first()
            assert row.cost==expected
            assert row.phone=='507' and row.task=='transcripcion_audio'
    def fail(**kw): raise RuntimeError('provider down')
    monkeypatch.setattr(t.cliente_openai.audio.transcriptions,'create',fail)
    with pytest.raises(RuntimeError): t.transcribir_audio(b'audio')
    with c.SessionSesiones() as db: assert db.query(c.CostEvent).filter_by(status='error').one().cost is None


def test_expense_validation_idempotency_and_separate_totals():
    body=GastoBot(request_id='expense-1',proveedor='servidor',concepto='Servidor',fecha='2026-10-08',monto_usd='12.50')
    assert c.save_expense(body,'alexander')==c.save_expense(body,'alexander')
    changed=body.model_copy(update={'monto_usd':Decimal('13')})
    with pytest.raises(ValueError): c.save_expense(changed,'alexander')
    data=c.analytics(date(2026,10,8),date(2026,10,8))
    assert data['total_confirmado']==12.5 and data['totales']['costo_usd']==0
    for bad in ('-1','NaN','Infinity','0'):
        with pytest.raises(ValidationError): GastoBot(request_id='expense-2',proveedor='meta',concepto='Test',fecha='2026-10-08',monto_usd=bad)
    with pytest.raises(ValidationError): GastoBot(request_id='expense-2',proveedor='meta',concepto='   ',fecha='2026-10-08',monto_usd=1)


def test_invalid_ranges():
    with pytest.raises(ValueError): c.analytics(date(2026,1,2),date(2026,1,1))
    with pytest.raises(ValueError): c.analytics(date(2000,1,1),date(2026,1,1))
    with pytest.raises(ValueError): c.analytics(date(2026,1,1),date(2026,1,1),provider='invalid')


def test_anthropic_wrapper_tracks_failure_and_preserves_reply_on_accounting_failure(monkeypatch):
    def fail(**kw): raise RuntimeError('service')
    with pytest.raises(RuntimeError): c.call_anthropic(NS(messages=NS(create=fail)), model='claude-sonnet-5')
    with c.SessionSesiones() as db: assert db.query(c.CostEvent).one().status=='error'
    def broken_db(): raise RuntimeError('db')
    monkeypatch.setattr(c,'SessionSesiones',broken_db)
    r=response(input_tokens=1,output_tokens=1)
    assert c.call_anthropic(NS(messages=NS(create=lambda **kw:r)),model='claude-sonnet-5') is r


def test_expense_archive_restore_keeps_audit():
    body=GastoBot(request_id='expense-archive',proveedor='meta',concepto='Factura',fecha='2026-10-08',monto_usd='8')
    ident=c.save_expense(body,'alexander')
    c.archive_expense(ident,True,'luis')
    data=c.analytics(date(2026,10,8),date(2026,10,8))
    assert data['total_confirmado']==0 and data['gastos_confirmados'][0]['archivado'] is True
    with c.SessionSesiones() as db:
        row=db.get(c.ConfirmedExpense,ident)
        assert row.modified_by=='luis' and row.modified_at is not None
    c.archive_expense(ident,False,'alexander')
    assert c.analytics(date(2026,10,8),date(2026,10,8))['total_confirmado']==8


def test_cost_routes_auth_dates_and_bad_invoice():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import panel
    app=FastAPI();app.include_router(panel.router)
    client=TestClient(app)
    assert client.get('/panel/costos').status_code==401
    app.dependency_overrides[panel.verificar_credenciales_panel]=lambda:'alexander'
    assert client.get('/panel/costos?desde=2026-10-08&hasta=2026-10-08').status_code==200
    assert client.get('/panel/costos?desde=2026-10-09&hasta=2026-10-08').status_code==422
    assert client.get('/panel/costos?proveedor=invalid').status_code==422
    assert client.post('/panel/costos/gastos',json={'request_id':'route-1234','proveedor':'meta','concepto':'test','fecha':'2026-10-08','monto_usd':'NaN'}).status_code==422
    body={'request_id':'route-1234','proveedor':'meta','concepto':'test','fecha':'2026-10-08','monto_usd':'2'}
    r=client.post('/panel/costos/gastos',json=body)
    assert r.status_code==200
    assert client.post('/panel/costos/gastos',json=body).json()['id']==r.json()['id']
    assert client.post(f"/panel/costos/gastos/{r.json()['id']}/estado",json={'accion':'archivar'}).status_code==200
    assert client.post('/panel/costos/gastos/999999/estado',json={'accion':'archivar'}).status_code==404


def test_bad_metrics_do_not_break_model_reply():
    r=NS(id='broken-metrics',model='claude-sonnet-5',usage=NS(input_tokens='not a number'))
    assert c.call_anthropic(NS(messages=NS(create=lambda **kw:r)),model='claude-sonnet-5') is r


def test_compatible_overview_and_chat_include_openai_without_duplicates():
    from app.db.session_store import obtener_resumen_uso, obtener_uso_por_telefono
    c.record_anthropic(response(input_tokens=1000,output_tokens=0), '507')
    c.record_event(provider='openai',model='whisper-1',task='transcripcion_audio',phone='507',audio_seconds=60,cost=Decimal('.006'))
    summary=obtener_resumen_uso(30)
    assert summary['costo_usd']==pytest.approx(.008)
    assert summary['tokens_totales']==1000
    chat=obtener_uso_por_telefono('507')
    assert chat['costo_usd']==pytest.approx(.008) and chat['llamadas']==2


def test_vision_retry_and_redactor_are_instrumented(monkeypatch):
    from app.ai import orchestrator
    from app.tools import comprobantes
    reply=response(input_tokens=1000,output_tokens=100)
    reply.content=[NS(type='text',text='Mensaje confirmado')]
    monkeypatch.setattr(orchestrator.cliente_claude.messages,'create',lambda **kw:reply)
    assert orchestrator.redactar_respuesta_de_asesor('Hola','Confirmado','507')=='Mensaje confirmado'
    with c.SessionSesiones() as db:
        assert db.query(c.CostEvent).one().task=='redaccion_asistida'
    # Static guard: both vision attempts flow through the single metered wrapper.
    import inspect
    source=inspect.getsource(comprobantes)
    assert "task='analisis_imagen'" in source
    assert 'cliente_claude.messages.create' not in source
