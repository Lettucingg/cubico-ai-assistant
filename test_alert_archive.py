import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session_store import AlertaArchivada
from app.services import alert_archive
from app.api import panel

@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///'+str(tmp_path/'alerts.db'), connect_args={'check_same_thread':False})
    AlertaArchivada.__table__.create(engine)
    monkeypatch.setattr(alert_archive,'SessionSesiones',sessionmaker(bind=engine))
    monkeypatch.setattr(panel,'USUARIOS_PANEL',{'alexander':'test','luis':'test'})
    app=FastAPI();app.include_router(panel.router)
    with TestClient(app) as c:
        yield c
    engine.dispose()

PAYLOAD={'clave':'["mensaje","507",1]','titulo':'Nuevo mensaje','descripcion':'Consulta pendiente','motivo':'descartada'}

def test_auth_required_and_input_validated(client):
    assert client.get('/panel/alertas/papelera').status_code==401
    assert client.post('/panel/alertas/archivar',json=PAYLOAD).status_code==401
    assert client.post('/panel/alertas/1/restaurar').status_code==401
    for changes in ({'motivo':'eliminar'},{'clave':''},{'clave':'x'*2001},{'titulo':''}):
        assert client.post('/panel/alertas/archivar',json={**PAYLOAD,**changes},auth=('alexander','test')).status_code==422

def test_archive_shared_persistent_idempotent_and_restore(client):
    a=client.post('/panel/alertas/archivar',json=PAYLOAD,auth=('alexander','test')).json()
    assert a['usuario']=='alexander' and a['motivo']=='descartada'
    again=client.post('/panel/alertas/archivar',json=PAYLOAD,auth=('luis','test')).json()
    assert again['id']==a['id'] and again['usuario']=='alexander'
    assert client.get('/panel/alertas/papelera',auth=('luis','test')).json()==[a]
    assert alert_archive.listar_archivadas()==[a]  # Separate database connection.
    new=client.post('/panel/alertas/archivar',json={**PAYLOAD,'clave':'["mensaje","507",2]','motivo':'resuelta'},auth=('luis','test')).json()
    assert new['id']!=a['id']
    for _ in range(2):
        assert client.post(f'/panel/alertas/{a["id"]}/restaurar',auth=('luis','test')).status_code==200
    assert alert_archive.listar_archivadas()==[new]
