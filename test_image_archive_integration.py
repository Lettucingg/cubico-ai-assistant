import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.core.config import settings
from app.services import image_archive as archive
from app.tools import comprobantes as receipts
from app.api import panel, whatsapp

PNG = b"\x89PNG\r\n\x1a\n" + b"fixture-image-bytes"


@pytest.fixture(autouse=True)
def private_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CUBICO_MEDIA_DIR", str(tmp_path / "private"))
    return tmp_path / "private"


def test_archived_photo_does_not_contact_meta(monkeypatch):
    archive.save_image("cached", PNG)
    monkeypatch.setattr(receipts.httpx, "AsyncClient", Mock(side_effect=AssertionError("No Meta call expected")))
    assert asyncio.run(receipts.descargar_imagen_de_whatsapp("cached")) == PNG


def test_download_of_old_photo_is_archived(monkeypatch):
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def get(self, url, **kwargs):
            request = httpx.Request("GET", url)
            if "graph.facebook.com" in url:
                return httpx.Response(200, json={"url": "https://media.example.test/image"}, request=request)
            return httpx.Response(200, content=PNG, headers={"content-type": "image/png"}, request=request)
    monkeypatch.setattr(receipts.httpx, "AsyncClient", lambda **kwargs: Client())
    assert asyncio.run(receipts.descargar_imagen_de_whatsapp("old-image")) == PNG
    assert archive.read_image("old-image") == PNG


def test_archive_write_failure_does_not_discard_download(monkeypatch):
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def get(self, url, **kwargs):
            request = httpx.Request("GET", url)
            if "graph.facebook.com" in url:
                return httpx.Response(200, json={"url": "https://media.example.test/image"}, request=request)
            return httpx.Response(200, content=PNG, headers={"content-type": "image/png"}, request=request)
    monkeypatch.setattr(receipts.httpx, "AsyncClient", lambda **kwargs: Client())
    monkeypatch.setattr(receipts, "save_image", Mock(side_effect=OSError("full disk")))
    assert asyncio.run(receipts.descargar_imagen_de_whatsapp("disk-failure")) == PNG
    assert archive.read_image("disk-failure") is None


def test_incoming_photo_is_archived_before_buffer_and_push(monkeypatch):
    calls = []
    monkeypatch.setattr(whatsapp, "obtener_o_crear_sesion", lambda _: SimpleNamespace(codigo_cliente_verificado=None))
    monkeypatch.setattr(whatsapp, "agregar_al_historial", lambda *a, **k: calls.append("history"))
    async def download(media_id):
        calls.append("archive")
        return PNG
    async def buffer(message):
        assert calls[:2] == ["history", "archive"]
    async def push(*args):
        assert calls[:2] == ["history", "archive"]
    monkeypatch.setattr(whatsapp, "descargar_imagen_de_whatsapp", download)
    monkeypatch.setattr(whatsapp, "agregar_mensaje_a_buffer", buffer)
    monkeypatch.setattr(whatsapp, "notificar_panel_push", push)
    asyncio.run(whatsapp.procesar_entrada_con_push({"telefono": "50700000000", "tipo": "image", "texto": None, "media_id": "incoming", "message_id": "msg"}))


def test_outgoing_panel_image_is_archived(monkeypatch):
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, url, **kwargs):
            return httpx.Response(200, json={"id": "outgoing"}, request=httpx.Request("POST", url))
    monkeypatch.setattr(whatsapp.httpx, "AsyncClient", lambda **kwargs: Client())
    assert asyncio.run(whatsapp.subir_media_whatsapp(PNG, "image/png", "photo.png")) == "outgoing"
    assert archive.read_image("outgoing") == PNG


def test_panel_auth_ownership_and_image_mime(monkeypatch):
    app = FastAPI()
    app.include_router(panel.router)
    session = SimpleNamespace(comprobante_media_id="allowed", obtener_historial=lambda: [])
    monkeypatch.setattr(panel, "obtener_sesion_existente", lambda phone: session)
    archive.save_image("allowed", PNG)
    download = AsyncMock(side_effect=receipts.descargar_imagen_de_whatsapp)
    monkeypatch.setattr(panel, "descargar_imagen_de_whatsapp", download)
    with TestClient(app) as client:
        assert client.get("/panel/imagen/50700000000/allowed").status_code in (401, 403)
        download.assert_not_called()
        app.dependency_overrides[panel.verificar_credenciales_panel] = lambda: "operator"
        assert client.get("/panel/imagen/50700000000/other-customer-image").status_code == 404
        download.assert_not_called()
        response = client.get("/panel/imagen/50700000000/allowed")
        assert response.status_code == 200
        assert response.content == PNG
        assert response.headers["content-type"] == "image/png"
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
