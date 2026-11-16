"""Los pins se conservan antes del aviso y se pueden usar como enlaces opcionales."""
import asyncio
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.api import whatsapp as wa
from app.db import session_store as store
from app.services.delivery_cases import ubicacion_en_chat


def payload(location):
    return {"entry": [{"changes": [{"value": {"messages": [{
        "from": "50760000000", "id": "LOCATION-1", "timestamp": "1794859200",
        "type": "location", "location": location,
    }]}}]}]}


def test_native_pin_extracted_without_media():
    msg = wa.extraer_mensaje_entrante(payload({"latitude": 8.99, "longitude": -79.5, "address": "Recepción"}))
    assert msg["tipo"] == "location" and msg["media_id"] is None
    assert msg["ubicacion"] == {"latitude": 8.99, "longitude": -79.5}
    assert "https://www.google.com/maps/" in msg["texto"]


@pytest.mark.parametrize("location", [
    {"latitude": True, "longitude": -79.5}, {"latitude": 91, "longitude": 0},
    {"latitude": "8.99", "longitude": -79.5}, {}, {"latitude": 0, "longitude": float("nan")},
])
def test_invalid_pin_is_ignored(location):
    assert wa.extraer_mensaje_entrante(payload(location)) is None


def test_pin_is_durable_before_push_and_suggested_to_delivery(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'locations.db'}")
    store.BaseSesiones.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(store, "SessionSesiones", factory)
    msg = wa.extraer_mensaje_entrante(payload({"latitude": 8.99, "longitude": -79.5}))
    calls = []
    async def inspect(*_):
        s = store.obtener_sesion_existente("50760000000")
        assert s.obtener_historial()[0]["ubicacion"]["latitude"] == 8.99
        assert ubicacion_en_chat(s)["tipo"] == "pin"
        calls.append(True)
    monkeypatch.setattr(wa, "agregar_mensaje_a_buffer", inspect)
    monkeypatch.setattr(wa, "notificar_panel_push", inspect)
    asyncio.run(wa.procesar_entrada_con_push(msg))
    assert len(calls) == 2
