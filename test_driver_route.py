"""Ruta personal: nunca confundir consulta, carga, despacho y entrega."""
from copy import deepcopy
from datetime import date
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import session_store as store
from app.services import driver_route as route
from app.api import panel

DAY = "2026-11-16"  # lunes


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'route.db'}", connect_args={"check_same_thread": False})
    store.BaseSesiones.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(store, "SessionSesiones", factory)
    monkeypatch.setattr(route, "hoy", lambda: date.fromisoformat(DAY))
    return factory


def stop(key="a", **changes):
    p = {"tipo": "domicilio", "telefono": "50760000001", "nombre": "Cliente " + key,
         "codigo_cliente": "CBC-" + key, "paquetes": "TRACK-" + key,
         "pago_resuelto": True, "monto_pendiente": 0, "requiere_verificacion": False,
         "requiere_factura": False, "paquetes_preparados": True, "domicilio_coordinado": True,
         "ficha_domicilio": {"clave": key, "token": "token-" + key, "direccion": "Dirección " + key,
             "zona": "centro", "fecha_confirmada": DAY, "hora_desde": "", "hora_hasta": "",
             "faltantes": [], "listo_para_coordinar": True}}
    ficha = changes.pop("ficha", {})
    p.update(changes)
    p["ficha_domicilio"].update(ficha)
    return p


def view(stops, user="alexander", zona="todas", fecha=DAY):
    return route.construir_ruta(stops, user, fecha, zona)


def save(r, *, order=None, loaded=None, user="alexander"):
    body = {"fecha": r["fecha"], "zona": r["zona"], "token": r["token"],
            "orden": order if order is not None else [p["id"] for p in r["paradas"]],
            "cargadas": loaded if loaded is not None else []}
    route.guardar_plan(r, user, body)


def test_get_is_read_only_and_filters_confirmed_date_zone_and_delivery_type(db):
    stops = [stop(), stop("other-day", ficha={"fecha_confirmada": "2026-11-17"}),
             stop("east", ficha={"zona": "este"}), stop("unplanned", ficha={"fecha_confirmada": "", "faltantes": ["fecha"], "listo_para_coordinar": False}),
             stop("pickup", tipo="retiro")]
    r = view(stops, zona="centro")
    assert [p["id"] for p in r["paradas"]] == ["a"]
    assert [p["id"] for p in r["sin_programar"]] == ["unplanned"]
    assert not r["puede_recorrer"] and not r["paradas"][0]["cargada"]
    with db() as session:
        assert session.query(store.PlanRuta).count() == 0


@pytest.mark.parametrize("change", [
    {"pago_resuelto": False}, {"monto_pendiente": 10}, {"monto_pendiente": None},
    {"monto_pendiente": float("nan")}, {"monto_pendiente": True}, {"monto_pendiente": "unknown"},
    {"paquetes_preparados": False}, {"domicilio_coordinado": False}, {"requiere_verificacion": True},
    {"requiere_factura": True}, {"paquetes": ""}, {"telefono": "bad"},
    {"ficha": {"listo_para_coordinar": False, "faltantes": ["dirección"]}},
])
def test_only_fully_reviewed_paid_prepared_cases_enter_navigation(db, change):
    r = view([stop(**change)])
    assert not r["paradas"] and len(r["pendientes"]) == 1
    assert not r["puede_recorrer"]


def test_default_order_is_time_then_priority_and_manual_order_is_persistent(db):
    stops = [stop("normal"), stop("priority", ficha={"prioridad": "alta"}),
             stop("early", ficha={"hora_desde": "07:00", "hora_hasta": "08:00"})]
    r = view(stops)
    assert [p["id"] for p in r["paradas"]] == ["early", "priority", "normal"]
    save(r, order=["normal", "early", "priority"], loaded=["normal", "early", "priority"])
    updated = view(stops)
    assert [p["id"] for p in updated["paradas"]] == ["normal", "early", "priority"]
    assert updated["puede_recorrer"] and updated["orden_manual"]


def test_zone_filter_preserves_other_zones_loading_and_users_are_isolated(db):
    stops = [stop(), stop("b", ficha={"zona": "este"})]
    save(view(stops, zona="centro"), loaded=["a"])
    east = view(stops, zona="este")
    save(east, loaded=["b"])
    assert view(stops)["puede_recorrer"]
    assert not view(stops, user="teresa")["puede_recorrer"]
    assert view(stops, user="teresa")["revision"] == 0


@pytest.mark.parametrize("change", [
    {"ficha": {"token": "updated"}}, {"ficha": {"direccion": "Changed address"}},
    {"ficha": {"referencias": "Piso 3"}}, {"paquetes": "NEW-TRACKING"},
])
def test_changes_invalidate_previous_loading_verification(db, change):
    original = stop()
    save(view([original]), loaded=["a"])
    assert view([original])["paradas"][0]["cargada"]
    changed = stop(**change)
    assert not view([changed])["paradas"][0]["cargada"]
    assert not view([changed])["puede_recorrer"]


def test_new_debt_removes_loaded_stop_from_navigation(db):
    save(view([stop()]), loaded=["a"])
    r = view([stop(monto_pendiente=5, pago_resuelto=False)])
    assert not r["paradas"] and r["pendientes"][0]["pago_verificado"] is False


def test_weekends_future_dates_and_operational_suspension_block_mode(db):
    future = "2026-11-17"
    r = view([stop(ficha={"fecha_confirmada": future})], fecha=future)
    save(r, loaded=["a"])
    assert not view([stop(ficha={"fecha_confirmada": future})], fecha=future)["puede_recorrer"]
    with pytest.MonkeyPatch.context() as m:
        m.setattr(route, "hoy", lambda: date(2026, 11, 21))
        sat = view([stop(ficha={"fecha_confirmada": "2026-11-21"})], fecha="2026-11-21")
        save(sat, loaded=["a"])
        assert not view([stop(ficha={"fecha_confirmada": "2026-11-21"})], fecha="2026-11-21")["puede_recorrer"]
    assert not route.construir_ruta([stop()], "alexander", DAY, suspension={"suspendido": True})["puede_recorrer"]


def test_stale_tabs_and_changed_candidate_lists_cannot_overwrite_plan(db):
    r = view([stop()])
    save(r, loaded=["a"])
    with pytest.raises(ValueError, match="pestaña"):
        save(r)
    current = view([stop(), stop("new")])
    body = {"fecha": DAY, "zona": "todas", "token": r["token"], "orden": ["a"], "cargadas": []}
    with pytest.raises(ValueError, match="cambió"):
        route.guardar_plan(current, "alexander", body)
    assert view([stop()])["paradas"][0]["cargada"]


@pytest.mark.parametrize("changes", [{"orden": ["a", "a"]}, {"cargadas": ["unknown"]},
    {"orden": []}, {"cargadas": "a"}, {"usuario": "other"}])
def test_invalid_plan_does_not_write(db, changes):
    r = view([stop()])
    body = {"fecha": DAY, "zona": "todas", "token": r["token"], "orden": ["a"], "cargadas": []}
    body.update(changes)
    with pytest.raises(ValueError):
        route.guardar_plan(r, "alexander", body)
    with db() as session:
        assert session.query(store.PlanRuta).count() == 0


@pytest.mark.parametrize("fecha,zona", [("20261116", "todas"), ("2026-99-99", "todas"), (DAY, "unknown"), (None, "todas")])
def test_invalid_filters_are_rejected(db, fecha, zona):
    with pytest.raises(ValueError):
        view([], fecha=fecha, zona=zona)


def test_optional_map_never_copies_unsafe_url_or_forces_customer_pin(db):
    r = view([stop(ficha={"ubicacion_url": "javascript:alert(1)"})])
    assert r["paradas"][0]["ubicacion_url"] == ""
    assert r["paradas"][0]["lista"]


def test_authenticated_api_checks_live_cases_beyond_recent_chat_limit_and_has_no_financial_writes(db, monkeypatch):
    from app.services import operational_context
    monkeypatch.setattr(operational_context, "service_block", lambda _: None)
    monkeypatch.setattr(panel, "listar_todas_sesiones", lambda **_: (_ for _ in ()).throw(AssertionError("must not cap active routes")))
    monkeypatch.setattr(panel, "consultar_facturas_por_codigo", lambda _: {"encontrado": True, "cantidad_facturas": 1, "saldo_pendiente_total": 0, "facturas": []})
    monkeypatch.setattr(panel, "_nombre_cliente", lambda _: "Cliente real")
    from app.services import delivery_cases
    monkeypatch.setattr(delivery_cases, "hoy", lambda: date.fromisoformat(DAY))
    with db() as session:
        s = store.Sesion(telefono="50760000001", codigo_cliente_verificado="CBC-a", tipo_cliente_verificado="cbc",
            solicitud_domicilio_pendiente=True, paquetes_a_domicilio="TRACK-a", direccion_domicilio="Dirección",
            paquetes_preparados=True, domicilio_coordinado=False, entregado=False)
        session.add(s); session.commit()
    s = store.obtener_sesion_existente("50760000001")
    ficha = delivery_cases.obtener_ficha(s)
    saved = delivery_cases.guardar_ficha(s.telefono, {"zona": "centro", "fecha_confirmada": DAY}, ficha["token"], "operator")
    delivery_cases.coordinar_ficha(s.telefono, saved["token"])
    with db() as session:
        session.add(store.Sesion(telefono="50760000002", solicitud_domicilio_pendiente=True, entregado=True))
        session.commit()
    app = FastAPI(); app.include_router(panel.router)
    with TestClient(app) as client:
        assert client.get("/panel/ruta?fecha=" + DAY).status_code in (401, 403)
        assert client.post("/panel/ruta", json={}).status_code in (401, 403)
        app.dependency_overrides[panel.verificar_credenciales_panel] = lambda: "alexander"
        r = client.get("/panel/ruta?fecha=" + DAY).json()
        assert len(r["paradas"]) == 1
        selected = client.get("/panel/solicitudes?telefono=50760000001")
        assert selected.status_code == 200 and selected.json()[0]["tipo"] == "domicilio"
        key = r["paradas"][0]["id"]
        body = {"fecha": DAY, "zona": "todas", "token": r["token"], "orden": [key], "cargadas": [key]}
        result = client.post("/panel/ruta", json=body)
        assert result.status_code == 200 and result.json()["puede_recorrer"]
        assert client.post("/panel/ruta", json=body).status_code == 409
        assert client.get("/panel/ruta?fecha=invalid").status_code == 400
    after = store.obtener_sesion_existente("50760000001")
    assert not after.entregado and after.solicitud_domicilio_pendiente
    assert after.domicilio_coordinado and not after.pago_confirmado
    assert not after.obtener_historial()
