import asyncio
import json
from datetime import datetime,timedelta
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import session_store as store
from app.services import china_air_client as api,china_air_workflow as flow
from app.services.china_air_extraction import parse_extraction

PHONE='50760000002'
PACKAGES=[{'tracking':'TEST00000001','cliente':'CBC-0093','peso_kg':0.3,'lb_proveedor':1,'costo_proveedor':10,
           'contenido':'Carcasas de prueba','fecha_recepcion':'2026-10-26'}]

def rows_for(packages):
    return [{'ok':bool(p['cliente']), 'errores':[] if p['cliente'] else ['Falta el código del cliente'], 'avisos':[],
        'paquete':{'tracking':p['tracking'],'cliente':{'codigo':p['cliente'],'nombre':'Cliente de prueba'},
                   'lb_reales':1,'lb_volumen':0,'lb_cobrables':1,'tarifa_cliente':12,'cobro_estimado':12}} for p in packages]


@pytest.fixture
def setup(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'china.db'),connect_args={'check_same_thread':False})
    store.BaseSesiones.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    monkeypatch.setattr(flow,'SessionSesiones',factory)
    monkeypatch.setattr(api.settings,'CUBICO_BOT_KEY','test-key-not-real')
    monkeypatch.setattr(api.settings,'CUBICO_CHINA_AIR_LUIS_NUMBERS_JSON','["50760000001","50760000002"]')
    monkeypatch.setattr(api.settings,'CUBICO_CHINA_AIR_ENABLED',True)
    monkeypatch.setattr(api.settings,'CUBICO_INTERNAL_BASE_URL','http://127.0.0.1:3000')
    clock={'now':datetime(2026,11,5,19)};monkeypatch.setattr(flow,'now_utc',lambda:clock['now'])
    tell=AsyncMock();monkeypatch.setattr(flow,'tell',tell)
    extract=AsyncMock(return_value=([dict(p) for p in PACKAGES],[]));monkeypatch.setattr(flow,'extract',extract)
    preview=AsyncMock(side_effect=rows_for);monkeypatch.setattr(api,'preview',preview)
    register=AsyncMock(return_value=[{'registrado':True,'aviso_enviado':True}]);monkeypatch.setattr(api,'register',register)
    yield NS(db=factory,clock=clock,tell=tell,extract=extract,preview=preview,register=register)
    engine.dispose()


def incoming(setup,key,kind='text',text='',phone=PHONE):
    setup.clock['now']+=timedelta(seconds=1)
    msg={'telefono':phone,'message_id':key,'tipo':kind,'texto':text,'media_id':'media-'+key if kind=='image' else None}
    assert flow.enqueue(msg)
    return msg


def run():asyncio.run(flow.run_due())

def batch(setup):
    with setup.db() as db:
        row=db.query(flow.ChinaAirBatch).order_by(flow.ChinaAirBatch.updated.desc()).first()
        return flow.snapshot(row.id)


def prepare(setup):
    incoming(setup,'photo-1','image')
    incoming(setup,'text-1',text='Acabamos de recibir en la bodega en China para enviar vía aéreo. Peso físico 0.30 kg')
    run()
    setup.clock['now']+=timedelta(seconds=121);run()
    assert batch(setup)['stage']=='awaiting'


def test_only_two_luis_numbers_and_feature_flag_can_route(setup,monkeypatch):
    msg={'telefono':'50760000000','tipo':'image','message_id':'x'}
    assert not flow.should_handle(msg)
    with pytest.raises(ValueError):flow.enqueue(msg)
    assert flow.should_handle({**msg,'telefono':PHONE})
    assert not flow.should_handle({**msg,'telefono':PHONE,'tipo':'text','texto':'¿Cuánto cuesta China aéreo?'})
    assert flow.should_handle({**msg,'telefono':'50760000001'})
    assert not flow.should_handle({**msg,'telefono':PHONE,'tipo':'text','texto':'/responder 50760000000 hola'})
    monkeypatch.setattr(api.settings,'CUBICO_CHINA_AIR_ENABLED',False)
    assert not flow.should_handle({**msg,'telefono':PHONE})


def test_album_waits_for_quiet_period_collects_every_image_and_never_registers(setup):
    incoming(setup,'p1','image');run()
    setup.clock['now']+=timedelta(seconds=110)
    incoming(setup,'p2','image');incoming(setup,'txt',text='China aéreo, paquete 1 y 2');run()
    setup.clock['now']+=timedelta(seconds=110);run()
    setup.extract.assert_not_awaited();setup.register.assert_not_awaited()
    setup.clock['now']+=timedelta(seconds=11);run()
    assert len(setup.extract.call_args.args[0])==3
    assert len([x for x in setup.extract.call_args.args[0] if x['media_id']])==2
    setup.register.assert_not_awaited()


def test_confirmation_registers_only_once_and_only_as_luis(setup):
    prepare(setup)
    incoming(setup,'confirm',text='sí');run();run()
    setup.register.assert_awaited_once()
    assert setup.register.call_args.kwargs=={'phone':PHONE}
    assert batch(setup)['stage']=='done'
    assert 'Para Lynn' in setup.tell.call_args.args[1]
    assert not flow.enqueue({'telefono':PHONE,'message_id':'confirm','tipo':'text','texto':'sí'})
    run();assert setup.register.await_count==1


def test_missing_client_is_never_inferred_then_explicit_yes_code_repreviews(setup):
    unknown=[{**PACKAGES[0],'cliente':''}]
    setup.extract.return_value=(unknown,['Código cortado; no asignado'])
    prepare(setup)
    incoming(setup,'yes-no-code',text='sí');run();setup.register.assert_not_awaited()
    incoming(setup,'yes-code',text='sí, 0093');run()
    assert setup.register.call_args.args[0][0]['cliente']=='CBC-0093'
    assert setup.preview.await_count>=3


def test_correction_without_yes_always_shows_new_preview_before_write(setup):
    prepare(setup)
    incoming(setup,'correction',text='1 CBC-0079');run()
    setup.register.assert_not_awaited()
    assert json.loads(batch(setup)['packages_json'])[0]['cliente']=='CBC-0079'
    incoming(setup,'yes',text='sí');run()
    assert setup.register.call_args.args[0][0]['cliente']=='CBC-0079'


def test_changed_quote_needs_new_confirmation(setup):
    prepare(setup)
    original=rows_for(PACKAGES)
    changed=json.loads(json.dumps(original));changed[0]['paquete']['cobro_estimado']=15
    setup.preview.side_effect=None;setup.preview.return_value=changed
    incoming(setup,'yes',text='sí');run()
    setup.register.assert_not_awaited();assert batch(setup)['stage']=='awaiting'
    incoming(setup,'yes-2',text='sí');run()
    setup.register.assert_awaited_once()


def test_early_yes_is_not_confirmation_and_new_photos_invalidate_preview(setup):
    incoming(setup,'p1','image');incoming(setup,'early-yes',text='sí');run()
    setup.clock['now']+=timedelta(seconds=121);run();setup.register.assert_not_awaited()
    incoming(setup,'new-photo','image');incoming(setup,'yes-after-photo',text='sí');run()
    assert batch(setup)['stage']=='collecting';setup.register.assert_not_awaited()


def test_cancel_before_registration_and_status_does_not_start_empty_batch(setup):
    prepare(setup);incoming(setup,'cancel',text='cancelar');run()
    assert batch(setup)['stage']=='cancelled';setup.register.assert_not_awaited()
    incoming(setup,'status',text='/china estado');run()
    with setup.db() as db:
        assert db.query(flow.ChinaAirBatch).count()==1
        assert not db.query(flow.ChinaAirBatch).filter_by(closed=False).count()


def test_timeout_blocks_retries_after_worker_restart(setup):
    prepare(setup);setup.register.side_effect=TimeoutError('no response')
    incoming(setup,'yes',text='sí');run()
    assert batch(setup)['stage']=='uncertain'
    incoming(setup,'yes-again',text='sí');run();run()
    assert setup.register.await_count==1
    incoming(setup,'review',text='/china revisado');run()
    assert batch(setup)['closed']


def test_interrupted_claim_recovery_does_not_register(setup):
    prepare(setup)
    with setup.db() as db:
        row=db.query(flow.ChinaAirBatch).first();row.stage='saving';row.updated-=timedelta(minutes=11);db.commit()
    run();assert batch(setup)['stage']=='uncertain';setup.register.assert_not_awaited()


def test_partial_result_and_mail_failure_are_not_claimed_success(setup):
    two=[*PACKAGES,{**PACKAGES[0],'tracking':'TEST00000002','cliente':'CBC-0079'}]
    setup.extract.return_value=(two,[])
    setup.register.return_value=[{'registrado':True,'aviso_enviado':False},{'registrado':False,'errores':['Ya registrado']}]
    prepare(setup);incoming(setup,'yes',text='sí');run()
    text=setup.tell.call_args.args[1]
    assert '1 de 2' in text and 'correo no confirmado' in text and 'Ya registrado' in text
    assert 'Sí, continuar' not in text


def test_extraction_requires_evidence_and_does_not_assign_from_suggestions():
    payload={'es_aviso_aereo':True,'paquetes':[{**PACKAGES[0],'evidencia_cliente':'','observaciones':'Mismo remitente que CBC-0093'}],'avisos':[]}
    packages,warnings=parse_extraction(json.dumps(payload))
    assert packages[0]['cliente']=='' and warnings
    payload['es_aviso_aereo']=False
    with pytest.raises(ValueError):parse_extraction(json.dumps(payload))


def test_strict_payload_no_duplicates_invalid_weights_or_injection():
    assert api.Package(cliente='cbc 93').cliente=='CBC-0093'
    assert api.Package(cliente='CBC0079').cliente=='CBC-0079'
    assert api.Package(cliente='SFE').cliente=='SFE'
    for values in ([PACKAGES[0],PACKAGES[0]],[{**PACKAGES[0],'peso_kg':-1}],[{**PACKAGES[0],'peso_kg':float('nan')}],
                   [{**PACKAGES[0],'tracking':'DROP; TABLE'}],[{**PACKAGES[0],'confirmado_por':'cliente'}]):
        with pytest.raises(ValueError):api.validate_packages(values)


def test_api_contract_loopback_only_no_redirects_no_retries_and_header(monkeypatch):
    monkeypatch.setattr(api.settings,'CUBICO_CHINA_AIR_ENABLED',True)
    monkeypatch.setattr(api.settings,'CUBICO_BOT_KEY','test-only')
    monkeypatch.setattr(api.settings,'CUBICO_CHINA_AIR_LUIS_NUMBERS_JSON','["50760000001","50760000002"]')
    real=httpx.AsyncClient;calls=[]
    def handler(request):
        calls.append(request)
        assert request.headers['x-cubico-key']=='test-only'
        assert request.url.host=='127.0.0.1'
        data=json.loads(request.content)
        if request.url.path.endswith('previsualizar'):
            assert data=={'paquetes':PACKAGES}
            return httpx.Response(200,json={'resultados':rows_for(PACKAGES)})
        assert data=={'paquetes':PACKAGES,'confirmado_por':'Luis'}
        return httpx.Response(200,json={'resultados':[{'registrado':True,'aviso_enviado':True}]})
    def client(**kwargs):
        assert kwargs['follow_redirects'] is False and kwargs['trust_env'] is False
        return real(transport=httpx.MockTransport(handler),**kwargs)
    monkeypatch.setattr(api.httpx,'AsyncClient',client)
    monkeypatch.setattr(api.settings,'CUBICO_INTERNAL_BASE_URL','http://127.0.0.1:3000')
    asyncio.run(api.preview(PACKAGES));asyncio.run(api.register(PACKAGES,phone=PHONE))
    assert len(calls)==2
    with pytest.raises(ValueError):asyncio.run(api.register(PACKAGES,phone='50760000000'))
    assert len(calls)==2
    for url in ('https://cubico.com.pa','http://example.com:3000','http://127.0.0.1:3000/elsewhere','http://secret@127.0.0.1:3000'):
        monkeypatch.setattr(api.settings,'CUBICO_INTERNAL_BASE_URL',url)
        with pytest.raises(ValueError):api.local_url('recepciones')


def test_preview_singleton_shape_order_validation_and_no_prices_invented():
    assert api.preview_rows(rows_for(PACKAGES)[0],1)==rows_for(PACKAGES)
    with pytest.raises(ValueError):api.preview_rows({'ok':True},2)
    text=api.summary(PACKAGES,[{'ok':False,'errores':['Cliente desconocido'],'avisos':[]}])
    assert '$12' not in text and 'Cliente desconocido' in text


def test_all_five_air_cases_use_cubico_quotes_not_fixed_bot_tariffs(setup):
    cases=[('TEST00000001','CBC-0093',0.3,None,1,12),
           ('TEST00000002','',1.2,(36,21,25),9,108),
           ('TEST00000003','',0.7,(32,24,14),5,60),
           ('TEST00000004','CBC-0093',0.3,None,1,12),
           ('TEST00000005','CBC-0079',1.7,(30,13,9),4,46)]
    packages=[];rows=[]
    for track,code,weight,dimensions,pounds,cost in cases:
        p={**PACKAGES[0],'tracking':track,'cliente':code,'peso_kg':weight,'lb_proveedor':pounds,'costo_proveedor':pounds*10}
        if dimensions:p.update(zip(('largo_cm','ancho_cm','alto_cm'),dimensions))
        packages.append(p)
        r=rows_for([p])[0];r['paquete'].update(lb_cobrables=pounds,cobro_estimado=cost,tarifa_cliente=11.5 if code=='CBC-0079' else 12)
        rows.append(r)
    setup.extract.return_value=(packages,[]);setup.preview.side_effect=None;setup.preview.return_value=rows
    prepare(setup)
    text=setup.tell.call_args.args[1]
    assert '$108.00' in text and '$60.00' in text and '$46.00' in text and '¿Cliente?' in text
    setup.register.assert_not_awaited()


def test_missing_date_or_content_never_registers_even_when_server_ok(setup):
    setup.extract.return_value=([{**PACKAGES[0],'fecha_recepcion':None,'contenido':''}],[])
    prepare(setup);incoming(setup,'yes',text='sí');run()
    setup.register.assert_not_awaited()
    assert batch(setup)['stage']=='awaiting'


def test_registration_unreadable_body_is_not_retried_or_treated_success(monkeypatch):
    monkeypatch.setattr(api.settings,'CUBICO_CHINA_AIR_ENABLED',True)
    monkeypatch.setattr(api.settings,'CUBICO_BOT_KEY','test-only')
    monkeypatch.setattr(api.settings,'CUBICO_CHINA_AIR_LUIS_NUMBERS_JSON','["50760000001","50760000002"]')
    monkeypatch.setattr(api.settings,'CUBICO_INTERNAL_BASE_URL','http://127.0.0.1:3000')
    real=httpx.AsyncClient;posts=[]
    def handler(request):
        posts.append(request)
        return httpx.Response(200,json={'ok':True})
    monkeypatch.setattr(api.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    with pytest.raises(ValueError):asyncio.run(api.register(PACKAGES,phone=PHONE))
    assert len(posts)==1


def test_per_message_and_batch_claims_are_compare_and_swap(setup):
    prepare(setup);state=batch(setup)
    assert flow.update(state['id'],expected_stage='awaiting',expected_version=state['version'],stage='confirming')
    assert not flow.update(state['id'],expected_stage='awaiting',expected_version=state['version'],stage='saving')
    setup.register.assert_not_awaited()


def test_whatsapp_batched_album_is_queued_before_team_command_router(setup,monkeypatch):
    from fastapi import BackgroundTasks
    from app.api import whatsapp
    from datetime import timezone
    monkeypatch.setattr(whatsapp,'NUMEROS_EQUIPO',[PHONE])
    monkeypatch.setattr(whatsapp,'record_whatsapp_receipts',lambda _:None)
    monkeypatch.setattr(whatsapp,'registrar_mensaje_entrante_una_vez',lambda _:True)
    send=AsyncMock();monkeypatch.setattr(whatsapp,'enviar_mensaje_whatsapp',send)
    timestamp=str(int(datetime.now(timezone.utc).timestamp()))
    messages=[{'from':PHONE,'id':'batched-photo-1','timestamp':timestamp,'type':'image','image':{'id':'media-one'}},
              {'from':PHONE,'id':'batched-photo-2','timestamp':timestamp,'type':'image','image':{'id':'media-two'}},
              {'from':PHONE,'id':'batched-text','timestamp':timestamp,'type':'text','text':{'body':'Paquete 1: cotización y medidas adjuntas'}}]
    payload={'entry':[{'changes':[{'value':{'messages':messages}}]}]}
    response=asyncio.run(whatsapp._procesar_payload_whatsapp(payload,BackgroundTasks()))
    assert response['status']=='lote_procesado'
    with setup.db() as db:
        assert db.query(flow.ChinaAirInbox).count()==3
    send.assert_not_awaited();setup.register.assert_not_awaited()


def test_vision_receives_all_images_in_one_metered_call(setup,monkeypatch):
    from app.services import china_air_extraction as extraction
    from app.tools import comprobantes
    downloader=AsyncMock(return_value=b'\xff\xd8test-photo')
    monkeypatch.setattr(comprobantes,'descargar_imagen_de_whatsapp',downloader)
    monkeypatch.setattr(extraction,'Anthropic',lambda **kwargs:NS())
    calls=[]
    payload={'es_aviso_aereo':True,'paquetes':[{**PACKAGES[0],'evidencia_cliente':'Foto 3: hoja CBC-0093'}],'avisos':[]}
    def call(client,**kwargs):
        calls.append(kwargs)
        return NS(stop_reason='end_turn',content=[NS(type='text',text=json.dumps(payload))])
    monkeypatch.setattr(extraction,'call_anthropic',call)
    messages=[{'texto':'China aéreo' if i==0 else '', 'media_id':f'photo-{i}'} for i in range(15)]
    packages,_=asyncio.run(extraction.extract(messages,PHONE))
    assert packages[0]['cliente']=='CBC-0093' and downloader.await_count==15 and len(calls)==1
    assert len([b for b in calls[0]['messages'][0]['content'] if b['type']=='image'])==15
    assert calls[0]['task']=='china_aereo_lectura_lote'
    with pytest.raises(ValueError):asyncio.run(extraction.extract(messages,'50760000000'))


def test_same_timestamp_preserves_album_arrival_order_before_confirmation(setup):
    prepare(setup);setup.clock['now']+=timedelta(seconds=1)
    flow.enqueue({'telefono':PHONE,'message_id':'zzz-photo-first','tipo':'image','texto':'','media_id':'late-photo'})
    flow.enqueue({'telefono':PHONE,'message_id':'aaa-yes-second','tipo':'text','texto':'sí'})
    run()
    setup.register.assert_not_awaited()
    assert batch(setup)['stage']=='collecting'


def test_failed_durable_inbox_insert_allows_meta_redelivery(setup,monkeypatch):
    from fastapi import BackgroundTasks
    from app.api import whatsapp
    from datetime import timezone
    monkeypatch.setattr(whatsapp,'record_whatsapp_receipts',lambda _:None)
    original=flow.enqueue;attempts=[]
    def flaky(message):
        attempts.append(1)
        if len(attempts)==1:raise RuntimeError('simulated database interruption')
        return original(message)
    monkeypatch.setattr(flow,'enqueue',flaky)
    raw={'from':PHONE,'id':'china-durable-retry','timestamp':str(int(datetime.now(timezone.utc).timestamp())),
         'type':'image','image':{'id':'media-retry'}}
    payload={'entry':[{'changes':[{'value':{'messages':[raw]}}]}]}
    with pytest.raises(RuntimeError):asyncio.run(whatsapp._procesar_payload_whatsapp(payload,BackgroundTasks()))
    assert raw['id'] not in whatsapp.mensajes_entrantes_recientes
    result=asyncio.run(whatsapp._procesar_payload_whatsapp(payload,BackgroundTasks()))
    assert result['status']=='china_aereo_en_cola'
    with setup.db() as db:assert db.query(flow.ChinaAirInbox).filter_by(message_id=raw['id']).count()==1


def test_single_message_in_later_entry_is_not_dropped(setup,monkeypatch):
    from fastapi import BackgroundTasks
    from app.api import whatsapp
    from datetime import timezone
    monkeypatch.setattr(whatsapp,'record_whatsapp_receipts',lambda _:None)
    raw={'from':PHONE,'id':'china-later-entry','timestamp':str(int(datetime.now(timezone.utc).timestamp())),
         'type':'image','image':{'id':'media-later'}}
    payload={'entry':[{'changes':[{'value':{'statuses':[]}}]},{'changes':[{'value':{'messages':[raw]}}]}]}
    result=asyncio.run(whatsapp._procesar_payload_whatsapp(payload,BackgroundTasks()))
    assert result['status']=='china_aereo_en_cola'
    with setup.db() as db:assert db.query(flow.ChinaAirInbox).filter_by(message_id=raw['id']).count()==1

@pytest.mark.parametrize('answer',['sí','si','ok','dale','correcto','Está correcto','👍'])
def test_confirmation_aliases_do_not_reextract_or_replace_supplier_cost(setup, answer):
    setup.extract.return_value=([{**PACKAGES[0], 'costo_proveedor':40}],[])
    prepare(setup)
    incoming(setup,'confirm-alias',text=answer);run()
    setup.register.assert_awaited_once()
    assert setup.register.call_args.args[0][0]['costo_proveedor']==40
    assert setup.extract.await_count==1


def test_unknown_confirmation_text_never_enters_extraction(setup):
    prepare(setup)
    incoming(setup,'unknown',text='Vi el resumen con $48');run()
    assert batch(setup)['stage']=='awaiting'
    setup.clock['now']+=timedelta(seconds=121);run()
    assert setup.extract.await_count==1
    setup.register.assert_not_awaited()


def test_ezra_three_cancelled_attempts_are_isolated(setup):
    ezra={**PACKAGES[0],'tracking':'SF5147491038495','cliente':'CBC-0079',
          'peso_kg':1.7,'lb_proveedor':4,'costo_proveedor':40,'fecha_recepcion':'2026-10-24'}
    setup.extract.return_value=([ezra],[])
    def preview(packages):
        result=rows_for(packages)
        result[0]['paquete'].update(lb_cobrables=4,cobro_estimado=48)
        return result
    setup.preview.side_effect=preview
    for attempt, cancel in enumerate(['/cancelar','cancelar','/china cancelar']):
        incoming(setup,f'photo-{attempt}','image')
        incoming(setup,f'lynn-{attempt}',text='Un paquete más. Lynn 24/10/2026. 4 lb $40')
        incoming(setup,f'identity-{attempt}','image',text='Ezra Angel CBC0079')
        run();setup.clock['now']+=timedelta(seconds=121);run()
        state=batch(setup)
        assert state['stage']=='awaiting'
        assert len(setup.extract.call_args.args[0])==3
        assert json.loads(state['packages_json'])[0]['costo_proveedor']==40
        summary=setup.tell.call_args.args[1]
        assert '1 paquete China' in summary and '4 lb' in summary
        assert '$48.00' in summary and 'Costo de Lynn: $40.00' in summary
        assert 'CBC-0079' in summary and 'SF5147491038495' in summary
        assert flow.should_handle({'telefono':PHONE,'tipo':'text','texto':cancel})
        incoming(setup,f'cancel-{attempt}',text=cancel);run()
        assert batch(setup)['closed'] and batch(setup)['packages_json'] is None
        with setup.db() as db:
            assert not db.query(flow.ChinaAirInbox).filter_by(batch_id=state['id']).filter(
                flow.ChinaAirInbox.media_id.isnot(None)).count()
    setup.register.assert_not_awaited()


def test_extraction_failure_logs_traceback(setup,caplog):
    setup.extract.side_effect=ValueError('Test: faltan medidas del paquete 3')
    incoming(setup,'failed-photo','image');run()
    setup.clock['now']+=timedelta(seconds=121);run()
    assert batch(setup)['stage']=='needs_input'
    assert 'faltan medidas del paquete 3' in caplog.text
    assert any(record.exc_info for record in caplog.records)


def test_requested_two_numbers_route_when_configured(setup,monkeypatch):
    numbers=['50769837308','50760705727']
    monkeypatch.setattr(api.settings,'CUBICO_CHINA_AIR_LUIS_NUMBERS_JSON',json.dumps(numbers))
    for phone in numbers:
        assert flow.should_handle({'telefono':phone,'tipo':'image'})
        assert flow.should_handle({'telefono':phone,'tipo':'text','texto':'/cancelar'})


def test_source_date_fallback_and_identification_sheet_count_guard():
    payload={'es_aviso_aereo':True,'paquetes':[{**PACKAGES[0],'fecha_recepcion':None,
        'evidencia_cliente':'Hoja CBC-0093'}],'avisos':[]}
    messages=[{'texto':'Lynn 24/10/2026: un paquete más'}]
    packages,_=parse_extraction(json.dumps(payload),messages)
    assert packages[0]['fecha_recepcion']=='2026-10-24'
    payload['paquetes'].append({**payload['paquetes'][0],'tracking':'TEST00000002'})
    with pytest.raises(ValueError,match='cantidad'):
        parse_extraction(json.dumps(payload),messages)
