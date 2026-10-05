import base64
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.session_store import PerfilPanel
from app.services import panel_profile
from app.api import panel


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'profile.db'), connect_args={'check_same_thread': False})
    PerfilPanel.__table__.create(engine)
    monkeypatch.setattr(panel_profile, 'SessionSesiones', sessionmaker(bind=engine))
    monkeypatch.setattr(panel, 'USUARIOS_PANEL', {'alexander': 'old-password', 'luis': 'other-password'})
    app = FastAPI()
    app.include_router(panel.router)
    with TestClient(app) as client:
        yield client
    engine.dispose()


def test_profile_auth_isolation_validation_and_persistence(client):
    auth = ('alexander', 'old-password')
    assert client.get('/panel/perfil').status_code == 401
    assert client.put('/panel/perfil', json={'nombre': 'Alex'}).status_code == 401
    assert client.put('/panel/perfil', json={'nombre': '   '}, auth=auth).status_code == 422
    assert client.put('/panel/perfil', json={'nombre': 'Alex', 'foto': 'data:image/svg+xml,<svg/>'}, auth=auth).status_code == 422
    foto = 'data:image/png;base64,' + 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jY1kAAAAASUVORK5CYII='
    assert client.put('/panel/perfil', json={'nombre': 'Alex', 'foto': foto}, auth=auth).status_code == 200
    assert panel_profile.get_profile('alexander')['foto'] == foto
    result = client.put('/panel/perfil', json={'nombre': 'Alex Cúbico', 'foto': None}, auth=auth)
    assert result.status_code == 200
    assert panel_profile.get_profile('alexander')['nombre'] == 'Alex Cúbico'
    assert client.get('/panel/perfil', auth=('luis', 'other-password')).json()['nombre'] == 'Luis'
    assert 'contrasena_hash' not in result.json()
    with panel_profile.SessionSesiones() as db:
        assert db.get(PerfilPanel, 'alexander').nombre == 'Alex Cúbico'


def test_password_old_revoked_and_new_survives_new_connection(client):
    old = ('alexander', 'old-password')
    endpoint = '/panel/perfil/contrasena'
    assert client.post(endpoint, json={'actual': 'wrong', 'nueva': 'nueva-segura-123'}, auth=old).status_code == 400
    assert client.post(endpoint, json={'actual': old[1], 'nueva': 'short'}, auth=old).status_code == 422
    assert client.post(endpoint, json={'actual': old[1], 'nueva': old[1]}, auth=old).status_code == 422
    assert client.post(endpoint, json={'actual': old[1], 'nueva': 'nueva-segura-123'}, auth=old).status_code == 200
    assert client.get('/panel/perfil', auth=old).status_code == 401
    assert client.get('/panel/perfil', auth=('alexander', 'nueva-segura-123')).status_code == 200
    assert client.get('/panel/perfil', auth=('luis', 'other-password')).status_code == 200
    with panel_profile.SessionSesiones() as db:
        encoded = db.get(PerfilPanel, 'alexander').contrasena_hash
        assert 'nueva-segura-123' not in encoded
    assert panel_profile.verify_password('nueva-segura-123', encoded)
    assert not panel_profile.authenticate('unknown', 'nueva-segura-123', panel.USUARIOS_PANEL)
