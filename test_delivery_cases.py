"""Ficha por operación, permisos y coordinación sin pagos ni mensajes automáticos."""
import asyncio
from datetime import timedelta
import json
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import session_store as store
from app.services import delivery_cases as delivery
from app.api import panel


@pytest.fixture
def db_factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'delivery.db'}", connect_args={"check_same_thread": False})
    store.BaseSesiones.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(store, "SessionSesiones", factory)
    with factory() as db:
        db.add(store.Sesion(telefono="50700000000", codigo_cliente_verificado="CBC-TEST",
            tipo_cliente_verificado="cbc", solicitud_domicilio_pendiente=True,
            paquetes_a_domicilio="TRACK-1", direccion_domicilio="San Francisco, calle de prueba",
            paquetes_preparados=True, entregado=False, domicilio_coordinado=False, historial_json="[]"))
        db.commit()
    return factory


def session(factory):
    with factory() as db:
        s = db.query(store.Sesion).one()
        db.expunge(s)
        return s


def next_day(weekday):
    d = delivery.hoy() + timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d.isoformat()


def save(factory, **changes):
    s = session(factory)
    ficha = delivery.obtener_ficha(s)
    datos = {"direccion": s.direccion_domicilio, "zona": "centro",
             "fecha_confirmada": next_day(0), "ubicacion_url": ""}
    datos.update(changes)
    return delivery.guardar_ficha(s.telefono, datos, ficha["token"], "alexander")


def test_get_does_not_create_or_confirm_case(db_factory):
    ficha = delivery.obtener_ficha(session(db_factory))
    assert ficha["revision"] == 0
    assert ficha["fecha_confirmada"] == ""
    assert not ficha["listo_para_coordinar"]
    with db_factory() as db:
        assert db.query(store.FichaDomicilio).count() == 0


def test_optional_location_and_distinct_requested_confirmed_dates(db_factory):
    ficha = save(db_factory, dia_solicitado="martes", fecha_solicitada=next_day(1),
                 horario_solicitado="Después de las 12", hora_desde="12:00", hora_hasta="14:00")
    assert ficha["listo_para_coordinar"]
    assert ficha["dia_solicitado"] == "martes"
    assert ficha["fecha_solicitada"] == next_day(1)
    assert ficha["fecha_confirmada"] == next_day(0)
    assert ficha["ubicacion_url"] == ""
    assert not session(db_factory).domicilio_coordinado


def test_zone_preferences_allow_reviewed_weekday_exceptions(db_factory):
    ficha = save(db_factory, zona="centro", fecha_confirmada=next_day(1))
    assert ficha["dias_preferentes"] == ["lunes", "miércoles"]
    assert ficha["listo_para_coordinar"]


def test_only_explicit_coordination_changes_status(db_factory):
    ficha = save(db_factory)
    delivery.coordinar_ficha("50700000000", ficha["token"])
    assert session(db_factory).domicilio_coordinado
    with db_factory() as db:
        assert db.query(store.FichaDomicilio).one().revision == 1


def test_requested_preferences_never_confirm_a_slot(db_factory):
    ficha = delivery.guardar_preferencias_cliente("50700000000",
        {"dia_solicitado": "lunes", "fecha_solicitada": next_day(0), "horario_solicitado": "7 a 8", "zona": "este"})
    assert ficha["fecha_confirmada"] == ""
    assert ficha["hora_desde"] == ""
    assert not session(db_factory).domicilio_coordinado
    with pytest.raises(ValueError):
        delivery.guardar_preferencias_cliente("50700000000", {"fecha_confirmada": next_day(0)})


def test_new_customer_preference_requires_new_review(db_factory):
    ficha = save(db_factory)
    delivery.coordinar_ficha("50700000000", ficha["token"])
    updated = delivery.guardar_preferencias_cliente("50700000000", {"horario_solicitado": "Solo después de las 14"})
    assert updated["fecha_confirmada"] == ""
    assert not session(db_factory).domicilio_coordinado


def test_unchanged_preferences_do_not_clear_coordination(db_factory):
    ficha = save(db_factory)
    delivery.coordinar_ficha("50700000000", ficha["token"])
    repeated = delivery.guardar_preferencias_cliente("50700000000", {})
    assert repeated["revision"] == ficha["revision"]
    assert session(db_factory).domicilio_coordinado


def test_save_change_invalidates_previous_coordination_and_retains_audit(db_factory):
    ficha = save(db_factory)
    delivery.coordinar_ficha("50700000000", ficha["token"])
    current = delivery.obtener_ficha(session(db_factory))
    updated = delivery.guardar_ficha("50700000000", {"referencias": "Recepción, piso 2"}, current["token"], "teresa")
    assert updated["revision"] == 2
    assert not session(db_factory).domicilio_coordinado
    with db_factory() as db:
        events = json.loads(db.query(store.FichaDomicilio).one().eventos_json)
        assert [e["usuario"] for e in events] == ["alexander", "teresa"]


def test_stale_operator_cannot_overwrite_saved_changes(db_factory):
    old = delivery.obtener_ficha(session(db_factory))
    delivery.guardar_ficha("50700000000", {"zona": "centro"}, old["token"], "alexander")
    with pytest.raises(ValueError, match="cambió"):
        delivery.guardar_ficha("50700000000", {"zona": "este"}, old["token"], "otro")
    assert delivery.obtener_ficha(session(db_factory))["zona"] == "centro"


def test_new_packages_do_not_inherit_old_schedule(db_factory):
    original = save(db_factory, barrio="Sector anterior", ubicacion_url="https://maps.app.goo.gl/fixture")
    with db_factory() as db:
        db.query(store.Sesion).one().paquetes_a_domicilio = "TRACK-NEW"
        db.commit()
    new = delivery.obtener_ficha(session(db_factory))
    assert new["clave"] != original["clave"]
    assert new["revision"] == 0 and new["fecha_confirmada"] == ""
    assert new["barrio"] == "" and new["ubicacion_url"] == ""
    with db_factory() as db:
        assert db.query(store.FichaDomicilio).count() == 1


def test_case_identity_includes_verified_customer(db_factory):
    original = save(db_factory)
    with db_factory() as db:
        db.query(store.Sesion).one().codigo_cliente_verificado = "CBC-OTHER"
        db.commit()
    new = delivery.obtener_ficha(session(db_factory))
    assert new["clave"] != original["clave"] and new["revision"] == 0


def test_changed_address_needs_review_before_coordination(db_factory):
    old = save(db_factory)
    with db_factory() as db:
        db.query(store.Sesion).one().direccion_domicilio = "Dirección nueva"
        db.commit()
    current = delivery.obtener_ficha(session(db_factory))
    assert current["direccion"] == "Dirección nueva"
    assert not current["listo_para_coordinar"]
    with pytest.raises(ValueError):
        delivery.coordinar_ficha("50700000000", old["token"])


@pytest.mark.parametrize("changes", [
    {"fecha_confirmada": "2026-99-99"}, {"fecha_solicitada": "20261117"},
    {"hora_desde": "25:00"}, {"zona": "desconocida"}, {"prioridad": "automatica"},
    {"ubicacion_url": "javascript:alert(1)"}, {"ubicacion_url": "https://google.com.evil.test/maps"},
    {"ubicacion_url": "https://user:pass@maps.google.com/maps"},
    {"ubicacion_url": "https://maps.google.com:444/maps"}, {"referencias": "a" * 1001},
])
def test_invalid_fields_leave_case_untouched(db_factory, changes):
    token = delivery.obtener_ficha(session(db_factory))["token"]
    with pytest.raises(ValueError):
        delivery.guardar_ficha("50700000000", changes, token, "tester")
    with db_factory() as db:
        assert db.query(store.FichaDomicilio).count() == 0


@pytest.mark.parametrize("changes", [
    {"fecha_confirmada": "2020-01-01"}, {"fecha_confirmada": next_day(5)},
    {"hora_desde": "14:00", "hora_hasta": "12:00"}, {"hora_desde": "12:00"},
    {"zona": "por_definir"}, {"direccion": ""},
])
def test_incomplete_or_unavailable_slot_cannot_be_coordinated(db_factory, changes):
    ficha = save(db_factory, **changes)
    assert not ficha["listo_para_coordinar"]
    with pytest.raises(ValueError):
        delivery.coordinar_ficha("50700000000", ficha["token"])
    assert not session(db_factory).domicilio_coordinado


def test_unprepared_or_closed_case_cannot_be_coordinated(db_factory):
    ficha = save(db_factory)
    with db_factory() as db:
        db.query(store.Sesion).one().paquetes_preparados = False
        db.commit()
    with pytest.raises(ValueError):
        delivery.coordinar_ficha("50700000000", ficha["token"])
    with db_factory() as db:
        db.query(store.Sesion).one().entregado = True
        db.commit()
    with pytest.raises(ValueError):
        delivery.guardar_ficha("50700000000", {"zona": "este"}, ficha["token"], "tester")


def test_maps_pin_and_link_are_suggestions_with_timestamp(db_factory):
    s = session(db_factory)
    s.historial_json = json.dumps([
        {"role": "user", "content": "https://maps.app.goo.gl/old", "timestamp": "2026-11-10T12:00:00Z"},
        {"role": "user", "tipo": "location", "ubicacion": {"latitude": 8.99, "longitude": -79.5}, "timestamp": "2026-11-16T12:00:00Z"}])
    found = delivery.ubicacion_en_chat(s)
    assert found["tipo"] == "pin" and "8.99,-79.5" in found["url"]
    assert found["timestamp"] == "2026-11-16T12:00:00Z"
    assert delivery.obtener_ficha(s)["ubicacion_url"] == ""


def test_only_customer_location_is_suggested(db_factory):
    s = session(db_factory)
    s.historial_json = json.dumps([
        {"role": "assistant", "content": "https://maps.app.goo.gl/office"},
        {"role": "user", "content": "https://evil.test/pin"}])
    assert delivery.ubicacion_en_chat(s) is None


def test_authenticated_api_saves_without_touching_payment_or_sending_message(db_factory, monkeypatch):
    app = FastAPI()
    app.include_router(panel.router)
    s = session(db_factory)
    ficha = delivery.obtener_ficha(s)
    with TestClient(app) as client:
        url = "/panel/solicitud/50700000000/domicilio"
        body = {"datos": {"zona": "centro", "fecha_confirmada": next_day(0)}, "token": ficha["token"]}
        assert client.post(url, json=body).status_code in (401, 403)
        app.dependency_overrides[panel.verificar_credenciales_panel] = lambda: "operator"
        response = client.post(url, json=body)
        assert response.status_code == 200
        assert response.json()["mensaje_enviado"] is False
        after = session(db_factory)
        assert after.pago_confirmado == s.pago_confirmado
        assert after.comprobante_media_id == s.comprobante_media_id
        assert not after.domicilio_coordinado
        assert client.post(url, json=body).status_code == 409


def test_panel_payment_gate_remains_required_for_coordination(db_factory, monkeypatch):
    from fastapi import HTTPException
    ficha = save(db_factory)
    monkeypatch.setattr(panel, "obtener_sesion_existente", lambda _: session(db_factory))
    def unpaid(_, _tipo=None):
        raise HTTPException(status_code=409, detail="Aún existe saldo pendiente")
    monkeypatch.setattr(panel, "_exigir_factura_pagada", unpaid)
    with pytest.raises(HTTPException):
        panel.actualizar_estado_solicitud("50700000000",
            {"tipo": "domicilio", "accion": "coordinar", "ficha_token": ficha["token"]}, usuario="operator")
    assert not session(db_factory).domicilio_coordinado


def test_panel_coordinates_reviewed_paid_case(db_factory, monkeypatch):
    ficha = save(db_factory)
    monkeypatch.setattr(panel, "obtener_sesion_existente", lambda _: session(db_factory))
    monkeypatch.setattr(panel, "_exigir_factura_pagada", lambda _, _tipo=None: {"saldo_pendiente_total": 0})
    result = panel.actualizar_estado_solicitud("50700000000",
        {"tipo": "domicilio", "accion": "coordinar", "ficha_token": ficha["token"]}, usuario="operator")
    assert result["status"] == "ok" and session(db_factory).domicilio_coordinado
