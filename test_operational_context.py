import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.services import operational_context as oc

NOW=datetime(2026,10,12,20,tzinfo=timezone.utc)

@pytest.fixture(autouse=True)
def database(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'ops.db'),connect_args={'check_same_thread':False})
    for model in (oc.OperationalNotice,oc.OperationalChange): model.__table__.create(engine)
    monkeypatch.setattr(oc,'SessionSesiones',sessionmaker(bind=engine))
    monkeypatch.setattr(oc,'now_utc',lambda:NOW)
    yield
    engine.dispose()


def data(**overrides):
    values=dict(titulo='Sin repartidor',tipo='sin_repartidor',areas=['domicilios'],efecto='suspendido',ruta='todas',trackings=[],
        mensaje_cliente='Los domicilios están suspendidos hoy.',alternativa='Retiro en el local si el paquete está listo.',notas_internas='SECRETO SOLO EQUIPO',
        inicio=NOW-timedelta(hours=1),fin=NOW+timedelta(hours=5),revisar_en=NOW+timedelta(hours=2))
    values.update(overrides);return values


def create(**values):
    return oc.create_notice(oc.NoticeCreate(request_id='request-'+str(len(oc.list_notices())+1),**data(**values)),'alexander')


def activate(row,**values):
    return oc.act_notice(row['id'],oc.NoticeAction(accion='activar',version=row['version'],**values),'alexander')


def test_draft_activation_pause_resolution_and_no_internal_leak():
    row=create();assert oc.active_context()==[]
    row=activate(row);assert oc.service_block('domicilios')['suspension_operativa']
    assert oc.service_block('retiros') is None
    prompt=oc.prompt_context(oc.active_context())
    assert 'Los domicilios' in prompt and 'SECRETO' not in prompt and 'notas_internas' not in prompt
    row=oc.act_notice(row['id'],oc.NoticeAction(accion='pausar',version=row['version']),'luis')
    assert oc.active_context()==[]
    row=activate(row)
    oc.act_notice(row['id'],oc.NoticeAction(accion='resolver',version=row['version']),'teresa')
    assert oc.active_context()==[]
    history=oc.history_notice(row['id'])
    assert [h['accion'] for h in history]==['resolver','activar','pausar','activar','creado']
    assert history[0]['usuario']=='teresa' and history[0]['aviso']['notas_internas']=='SECRETO SOLO EQUIPO'


def test_panama_start_end_boundary_and_review_not_expiry(monkeypatch):
    row=create(inicio='2026-10-12T16:00:00-05:00',fin='2026-10-12T18:00:00-05:00',revisar_en='2026-10-12T17:00:00-05:00')
    row=activate(row);assert row['estado_efectivo']=='programado';assert not oc.active_context()
    monkeypatch.setattr(oc,'now_utc',lambda:datetime(2026,10,12,21,tzinfo=timezone.utc))
    assert oc.active_context()
    monkeypatch.setattr(oc,'now_utc',lambda:datetime(2026,10,12,22,tzinfo=timezone.utc))
    assert oc.active_context() and oc.list_notices()[0]['requiere_revision']
    assert len(oc.due_reviews())==1 and oc.due_reviews()==[]
    monkeypatch.setattr(oc,'now_utc',lambda:datetime(2026,10,12,23,tzinfo=timezone.utc))
    assert not oc.active_context() and oc.list_notices()[0]['estado_efectivo']=='vencido'


def test_tracking_specific_scope_does_not_leak_to_other_package():
    activate(create(areas=['tracking'],trackings=['abc123456']))
    assert oc.active_context('Dónde está XYZ123456')==[]
    assert oc.active_context('Dónde está ABC123456')
    assert oc.active_context('Y ese paquete?', [{'role':'user','content':'ABC123456'}])
    assert oc.active_context('XYZ123456', [{'role':'user','content':'ABC123456'}])==[]
    assert oc.active_context('Mi paquete?', [{'role':'assistant','content':'ABC123456'}])==[]
    assert oc.active_context('ABC1234567')==[]
    assert oc.service_block('tracking','ABC123456')
    assert oc.service_block('tracking','XYZ123456') is None


def test_route_specific_notice_cannot_globally_suspend_deliveries():
    activate(create(ruta='miami_panama',areas=['aereo']))
    assert oc.active_context() and oc.service_block('domicilios') is None
    assert 'sin comprobar que pertenece a esa ruta' in oc.prompt_context(oc.active_context())


def test_overlap_conflicts_and_acknowledgement():
    a=activate(create());b=create()
    with pytest.raises(oc.ContextConflict) as error: activate(b)
    assert error.value.conflicts[0]['id']==a['id']
    assert len(oc.active_context())==1
    activate(b,aceptar_conflictos=True)
    assert len(oc.active_context())==2


def test_disjoint_scopes_routes_and_time_do_not_conflict():
    activate(create(areas=['aereo'],ruta='miami_panama'))
    activate(create(areas=['aereo'],ruta='china_panama'))
    activate(create(areas=['tracking'],trackings=['TRACK1111']))
    activate(create(areas=['tracking'],trackings=['TRACK2222']))
    activate(create(inicio=NOW+timedelta(hours=8),revisar_en=NOW+timedelta(hours=9),fin=NOW+timedelta(hours=10)))
    assert len(oc.active_context())==2
    assert sum(r["estado_efectivo"]=="activo" for r in oc.list_notices())==4


def test_active_edits_return_to_draft_stale_edit_rejected_audit_preserved():
    row=activate(create());before=row['version']
    edit=oc.NoticeEdit(**data(mensaje_cliente='Domicilios vuelven mañana.'),version=before)
    updated=oc.update_notice(row['id'],edit,'luis')
    assert updated['estado_efectivo']=='borrador' and oc.active_context()==[]
    with pytest.raises(ValueError): oc.update_notice(row['id'],edit,'teresa')
    with pytest.raises(ValueError): activate(row)
    assert len(oc.history_notice(row['id']))==3
    assert oc.history_notice(row['id'])[-1]['aviso']['mensaje_cliente']=='Los domicilios están suspendidos hoy.'


def test_idempotent_draft_and_validation():
    body=oc.NoticeCreate(**data(),request_id='same-request')
    assert oc.create_notice(body,'alexander')['id']==oc.create_notice(body,'alexander')['id']
    with pytest.raises(ValueError): oc.create_notice(body.model_copy(update={'titulo':'Otro título'}),'alexander')
    for overrides in ({'inicio':NOW.replace(tzinfo=None)}, {'fin':NOW-timedelta(hours=2)}, {'revisar_en':NOW-timedelta(hours=2)}, {'areas':['invalid']}, {'areas':['general','tracking']}, {'trackings':['<script>']}, {'titulo':'   '}, {'mensaje_cliente':'    '}):
        with pytest.raises(ValidationError): oc.NoticeData(**data(**overrides))


def test_overdue_review_reactivation_requires_new_date(monkeypatch):
    row=activate(create(fin=None))
    monkeypatch.setattr(oc,'now_utc',lambda:NOW+timedelta(hours=3))
    assert len(oc.due_reviews())==1
    row=oc.act_notice(row['id'],oc.NoticeAction(accion='revisado',version=row['version'],revisar_en=NOW+timedelta(hours=4)),'luis')
    assert not row['requiere_revision']
    monkeypatch.setattr(oc,'now_utc',lambda:NOW+timedelta(hours=4))
    assert len(oc.due_reviews())==1


def test_live_prompt_and_tool_cannot_confirm_suspended_delivery(monkeypatch):
    from app.ai import orchestrator as bot
    activate(create())
    replies=iter([NS(stop_reason='tool_use',content=[NS(type='tool_use',id='tool-1',name='solicitar_entrega_domicilio',input={'codigo_cliente':'CBC-1','direccion':'Calle'})]),NS(stop_reason='end_turn',content=[NS(type='text',text='Hoy no tenemos reparto; puedes retirar si está listo.')])])
    calls=[]
    def model(*args,**kw):calls.append(kw);return next(replies)
    monkeypatch.setattr(bot,'call_anthropic',model)
    monkeypatch.setattr(bot,'consultar_facturas_por_codigo',lambda *a:pytest.fail('No debe consultar ni crear un domicilio suspendido'))
    monkeypatch.setattr(bot,'actualizar_sesion',lambda *a,**k:pytest.fail('No debe cambiar sesión'))
    monkeypatch.setattr(bot,'obtener_oportunidad_comercial_abierta',lambda *a:None)
    text=bot.generar_respuesta('Quiero domicilio','507')
    assert 'no tenemos reparto' in text
    assert 'Los domicilios' in calls[0]['system'][-1]['text']
    assert 'SECRETO' not in str(calls)
    tool=[m for m in calls[-1]['messages'] if isinstance(m.get('content'),list) and any(isinstance(b,dict) and b.get('type')=='tool_result' for b in m['content'])]
    assert tool and 'suspension_operativa' in tool[0]['content'][0]['content']


def test_preview_isolated_without_transport_tools_or_session(monkeypatch):
    from app.services import cost_analytics
    calls=[]
    def model(*args,**kwargs):calls.append(kwargs);return NS(content=[NS(type='text',text='Hoy no hay repartidor.')])
    monkeypatch.setattr(cost_analytics,'call_anthropic',model)
    body=oc.ContextPreview(aviso=oc.NoticeData(**data()),pregunta='¿Me hacen domicilio?')
    result=oc.preview_response(body)
    assert result['respuesta']=='Hoy no hay repartidor.'
    assert result['simulacion'] and oc.list_notices()==[]
    assert 'tools' not in calls[0] and calls[0]['task']=='prueba_contexto_operativo'
    assert 'SECRETO' not in str(calls)
    body=oc.ContextPreview(aviso=oc.NoticeData(**data(trackings=['TRACK1111'])),pregunta='Dónde está TRACK2222')
    assert oc.preview_response(body)['aviso_propuesto_aplica'] is False


def test_payment_scheduler_holds_delivery_and_review_push_no_repeat(monkeypatch):
    from app import scheduler
    activate(create())
    sender=AsyncMock();notify=AsyncMock()
    monkeypatch.setattr(scheduler,'enviar_mensaje_whatsapp',sender)
    monkeypatch.setattr(scheduler,'notificar_equipo_domicilio',notify)
    asyncio.run(scheduler._continuar_domicilio_tras_pago_confirmado(NS(direccion_domicilio='Calle',telefono='507'),'FAC-1'))
    assert sender.await_count==0 and notify.await_count==0
    monkeypatch.setattr(oc,'now_utc',lambda:NOW+timedelta(hours=3))
    pushes=[];monkeypatch.setattr(scheduler,'_enviar_a_dispositivos',lambda payload:pushes.append(payload))
    asyncio.run(scheduler.revisar_contexto_operativo());asyncio.run(scheduler.revisar_contexto_operativo())
    assert len(pushes)==1 and pushes[0]['categoria']=='alertas' and pushes[0]['url']=='/admin?vista=operations'


def test_routes_auth_validation_versions_and_simulation_failure(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import panel
    app=FastAPI();app.include_router(panel.router);client=TestClient(app)
    assert client.get('/panel/contexto-operativo').status_code==401
    app.dependency_overrides[panel.verificar_credenciales_panel]=lambda:'alexander'
    body=oc.NoticeCreate(**data(),request_id='api-request').model_dump(mode='json')
    row=client.post('/panel/contexto-operativo',json=body).json()
    assert row['estado']=='borrador'
    assert client.post('/panel/contexto-operativo/'+str(row['id'])+'/estado',json={'accion':'activar','version':1}).status_code==200
    assert client.post('/panel/contexto-operativo/'+str(row['id'])+'/estado',json={'accion':'resolver','version':1}).status_code==409
    assert client.get('/panel/contexto-operativo/9999/historial').status_code==404
    bad={**body,'areas':['wrong']};assert client.post('/panel/contexto-operativo',json=bad).status_code==422
    monkeypatch.setattr(panel,'preview_response',lambda *a:(_ for _ in ()).throw(RuntimeError('secret API key')))
    r=client.post('/panel/contexto-operativo/prueba',json={'aviso':oc.NoticeData(**data()).model_dump(mode='json'),'pregunta':'Hola'})
    assert r.status_code==503 and 'secret' not in r.text


def test_tracking_tool_loads_specific_context_on_next_turn(monkeypatch):
    from app.ai import orchestrator as bot
    activate(create(areas=['tracking'],trackings=['TRACK1111'],efecto='informativo'))
    replies=iter([NS(stop_reason='tool_use',content=[NS(type='tool_use',id='lookup',name='consultar_tracking',input={'numero_tracking':'TRACK1111'})]),NS(stop_reason='end_turn',content=[NS(type='text',text='El tracking tiene un aviso registrado.')])])
    calls=[]
    monkeypatch.setattr(bot,'call_anthropic',lambda *a,**kw:(calls.append(kw),next(replies))[1])
    monkeypatch.setattr(bot,'obtener_oportunidad_comercial_abierta',lambda *a:None)
    monkeypatch.setattr(bot,'consultar_tracking',lambda *a:{'encontrado':True,'ubicacion':'Miami'})
    bot.generar_respuesta('Consulta el paquete de mi imagen','507')
    assert len(calls[0]['system'])==1
    assert 'TRACK1111' in calls[1]['system'][-1]['text']


def test_specific_retirement_notice_checked_against_verified_packages(monkeypatch):
    from app.ai import orchestrator as bot
    activate(create(areas=['retiros'],trackings=['TRACK1111']))
    replies=iter([NS(stop_reason='tool_use',content=[NS(type='tool_use',id='retire',name='avisar_retiro_paquete',input={'codigo_cliente':'CBC-1'})]),NS(stop_reason='end_turn',content=[NS(type='text',text='Este retiro necesita esperar por la incidencia.')])])
    calls=[]
    monkeypatch.setattr(bot,'call_anthropic',lambda *a,**kw:(calls.append(kw),next(replies))[1])
    monkeypatch.setattr(bot,'obtener_oportunidad_comercial_abierta',lambda *a:None)
    monkeypatch.setattr(bot,'consultar_paquetes_por_codigo',lambda *a:{'paquetes':[{'tracking':'TRACK1111','estado_cargo':'notificado'}]})
    monkeypatch.setattr(bot,'actualizar_sesion',lambda *a,**kw:pytest.fail('No debe crear retiro de ese paquete'))
    bot.generar_respuesta('Voy a retirar mi paquete','507')
    results=[m for m in calls[-1]['messages'] if isinstance(m.get('content'),list) and any(isinstance(b,dict) and b.get('type')=='tool_result' for b in m['content'])]
    assert 'suspension_operativa' in results[0]['content'][0]['content']


def test_active_limit_excludes_expired_notices(monkeypatch):
    for _ in range(20): activate(create(),aceptar_conflictos=True)
    candidate=create()
    with pytest.raises(ValueError,match='20 avisos'): activate(candidate,aceptar_conflictos=True)
    later=NOW+timedelta(hours=6)
    monkeypatch.setattr(oc,'now_utc',lambda:later)
    fresh=oc.update_notice(candidate['id'],oc.NoticeEdit(**data(inicio=later,revisar_en=later+timedelta(hours=1),fin=later+timedelta(hours=2)),version=candidate['version']),'alexander')
    assert activate(fresh)['estado_efectivo']=='activo'
