import json
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.services import delivery_diagnostics as d,cost_analytics as c


@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'diagnostics.db'))
    for table in (d.MetaDeliveryReceipt.__table__,c.CostEvent.__table__):table.create(engine)
    factory=sessionmaker(bind=engine)
    monkeypatch.setattr(d,'SessionSesiones',factory)
    monkeypatch.setattr(c,'SessionSesiones',factory)
    yield
    engine.dispose()


def payload(*receipts):return {'entry':[{'changes':[{'value':{'statuses':list(receipts)}}]}]}


def failed(**updates):
    return {'id':'wamid-test','recipient_id':'50760000000','status':'failed','timestamp':'1793844000',
            'errors':[{'code':131049,'title':'Provider title','message':'Provider message',
                       'error_data':{'details':'Actual provider detail'},'private_unused':'DO NOT STORE'}],**updates}


def test_terminal_failure_persists_full_diagnosis_without_session_history():
    c.record_whatsapp_receipts(payload(failed()))
    result=d.diagnostics('50760000000')
    assert result['solo_consulta'] and result['telefono']=='…0000'
    event=result['envios'][0]
    assert event['estado_actual']=='failed' and event['nota'] is None
    error=event['recibos'][0]['errores'][0]
    assert error=={'code':'131049','title':'Provider title','message':'Provider message','details':'Actual provider detail'}
    assert 'DO NOT STORE' not in json.dumps(result)


def test_duplicates_and_out_of_order_receipts_keep_error_and_latest_cost_status():
    c.record_whatsapp_receipts(payload(failed(),failed()))
    c.record_whatsapp_receipts(payload(failed(status='sent',errors=[])))
    event=d.diagnostics('50760000000')['envios'][0]
    assert event['estado_actual']=='failed' and len(event['recibos'])==2
    assert any(r['errores'] for r in event['recibos'])
    # A late HTTP acceptance must not overwrite a failure received first.
    c.record_whatsapp_response(NS(is_success=True,json=lambda:{'messages':[{'id':'wamid-test'}]}),'50760000000','template')
    assert d.diagnostics('50760000000')['envios'][0]['estado_actual']=='failed'


def test_batches_all_errors_missing_details_and_other_phones():
    c.record_whatsapp_receipts(payload(failed(),failed(id='wamid-other',recipient_id='50761111111',errors=[])))
    ours=d.diagnostics('50760000000')['envios']
    assert len(ours)==1 and ours[0]['message_id']=='wamid-test'
    other=d.diagnostics('50761111111')['envios'][0]
    assert other['recibos'][0]['errores']==[]


def test_old_failure_is_reported_without_fabricating_a_reason():
    with c.SessionSesiones() as db:
        db.add(c.CostEvent(provider='meta',model='whatsapp',task='mensaje_template',phone='50760000000',
                           status='failed',external_key='meta:old'));db.commit()
    event=d.diagnostics('50760000000')['envios'][0]
    assert event['estado_actual']=='failed' and event['recibos']==[] and 'no se puede reconstruir' in event['nota']


def test_independent_diagnosis_survives_cost_database_failure(monkeypatch):
    monkeypatch.setattr(c,'SessionSesiones',Mock(side_effect=RuntimeError('ledger failure')))
    c.record_whatsapp_receipts(payload(failed()))
    with d.SessionSesiones() as db:assert db.query(d.MetaDeliveryReceipt).one().status=='failed'


def test_error_text_bounded_and_no_read_triggers_sends(monkeypatch):
    c.record_whatsapp_receipts(payload(failed(errors=[{'code':1,'error_data':{'details':'x'*5000}}])))
    event=d.diagnostics('50760000000')['envios'][0]
    assert len(event['recibos'][0]['errores'][0]['details'])==1000
    assert d.diagnostics('50762222222')['envios']==[]
    with pytest.raises(ValueError):d.diagnostics('bad phone')
