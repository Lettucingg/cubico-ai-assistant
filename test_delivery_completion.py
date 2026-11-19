"""No cerrar otro lote, duplicar entregas ni perder el registro al abrir uno nuevo."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.db import session_store as store
from app.services import delivery_completion as service
from app.api import panel

PHONE='50760000001'

@pytest.fixture
def factory(tmp_path, monkeypatch):
    engine=create_engine(f"sqlite:///{tmp_path / 'completion.db'}",connect_args={'check_same_thread':False})
    store.BaseSesiones.metadata.create_all(engine)
    factory=sessionmaker(bind=engine)
    monkeypatch.setattr(store,'SessionSesiones',factory)
    with factory() as db:
        db.add(store.Sesion(telefono=PHONE,codigo_cliente_verificado='CBC-TEST',tipo_cliente_verificado='cbc',
            solicitud_domicilio_pendiente=True,paquetes_a_domicilio='TRACK-1, TRACK-2',
            direccion_domicilio='Dirección original',paquetes_preparados=True,domicilio_coordinado=True,
            entregado=False,solicitud_actualizada_en=datetime(2026,11,19,12)))
        db.commit()
    return factory

def token(factory,tipo='domicilio'):
    with factory() as db:return service.token_entrega(db.query(store.Sesion).one(),tipo)

def complete(t,verify=lambda s:None):
    return service.confirmar_entrega(PHONE,'domicilio',t,'alexander',verify,lambda s:'Cliente Prueba')

def test_durable_history_idempotence_and_replay_cannot_close_new_batch(factory):
    t=token(factory);first=complete(t);assert complete(t)['id']==first['id']
    with factory() as db:
        s=db.query(store.Sesion).one();assert s.entregado and not s.solicitud_domicilio_pendiente
        s.entregado=False;s.solicitud_domicilio_pendiente=True;s.paquetes_a_domicilio='NEW-TRACK';s.direccion_domicilio='Dirección nueva';db.commit()
    assert complete(t)['id']==first['id']
    with factory() as db:
        assert not db.query(store.Sesion).one().entregado
        assert db.query(store.EntregaPanel).count()==1
    saved=service.listar_entregas(first['fecha'])['entregas'][0]
    assert saved['paquetes']=='TRACK-1, TRACK-2' and saved['direccion']=='Dirección original'
    assert saved['confirmado_por']=='alexander' and saved['confirmado_en'].endswith('Z')

@pytest.mark.parametrize('field,value',[('paquetes_a_domicilio','OTRO'),('codigo_cliente_verificado','CBC-OTHER'),('domicilio_coordinado',False),('solicitud_domicilio_pendiente',False)])
def test_stale_case_rejected_without_record_or_close(factory,field,value):
    t=token(factory)
    with factory() as db:setattr(db.query(store.Sesion).one(),field,value);db.commit()
    with pytest.raises(ValueError,match='cambió'):complete(t)
    with factory() as db:assert db.query(store.EntregaPanel).count()==0;assert not db.query(store.Sesion).one().entregado

def test_unpaid_or_unprepared_cannot_be_marked_delivered(factory):
    def unpaid(s):raise HTTPException(status_code=409,detail='Pago pendiente')
    with pytest.raises(HTTPException):complete(token(factory),unpaid)
    with factory() as db:db.query(store.Sesion).one().paquetes_preparados=False;db.commit()
    with pytest.raises(ValueError,match='listos'):complete(token(factory))
    with factory() as db:assert db.query(store.EntregaPanel).count()==0;assert not db.query(store.Sesion).one().entregado

def test_record_and_case_update_rollback_together(factory):
    t=token(factory)
    def fail(db):raise RuntimeError('simulated persistence failure')
    event.listen(factory,'before_commit',fail)
    try:
        with pytest.raises(RuntimeError):complete(t)
    finally:event.remove(factory,'before_commit',fail)
    with factory() as db:assert db.query(store.EntregaPanel).count()==0;assert not db.query(store.Sesion).one().entregado

def test_concurrent_double_confirmation_keeps_single_record(factory):
    t=token(factory)
    with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(lambda _:complete(t),range(2)))
    assert rows[0]['id']==rows[1]['id']
    with factory() as db:assert db.query(store.EntregaPanel).count()==1

def test_panel_endpoint_requires_auth_and_uses_current_payment_guard(factory,monkeypatch):
    app=FastAPI();app.include_router(panel.router,prefix='/panel');client=TestClient(app)
    assert client.get('/panel/entregas').status_code==401
    app.dependency_overrides[panel.verificar_credenciales_panel]=lambda:'teresa'
    monkeypatch.setattr(panel,'obtener_sesion_existente',lambda _:object())
    monkeypatch.setattr(panel,'_exigir_factura_pagada',lambda s:None)
    monkeypatch.setattr(panel,'_nombre_cliente',lambda s:'Cliente Prueba')
    r=client.post('/panel/solicitud/'+PHONE+'/estado',json={'tipo':'domicilio','accion':'entregar','entrega_token':token(factory)})
    assert r.status_code==200 and r.json()['mensaje_enviado'] is False
    listed=client.get('/panel/entregas',params={'fecha':r.json()['entrega']['fecha']})
    assert listed.status_code==200 and listed.json()['entregas'][0]['confirmado_por']=='teresa'
    assert 'no-store' in listed.headers['cache-control']
    assert client.get('/panel/entregas?fecha=bad').status_code==400


def test_completing_domicile_keeps_separate_pickup_pending(factory):
    with factory() as db:
        s=db.query(store.Sesion).one();s.aviso_retiro_pendiente=True;s.paquetes_a_retirar='PICKUP-OTHER';db.commit()
    complete(token(factory))
    with factory() as db:
        s=db.query(store.Sesion).one()
        assert s.aviso_retiro_pendiente and not s.solicitud_domicilio_pendiente and not s.entregado
