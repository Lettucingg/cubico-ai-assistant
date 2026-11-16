"""Ejecuta la herramienta real aislada de IA, red y facturación de producción."""
import ast
from pathlib import Path
from types import SimpleNamespace
import pytest


def tool(monkeypatch, *, paid=True):
    source = ast.parse(Path("app/ai/orchestrator.py").read_text())
    node = next(n for n in ast.walk(source) if isinstance(n, ast.FunctionDef) and n.name == "_solicitar_entrega_domicilio")
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    state = SimpleNamespace(codigo_cliente_verificado="CBC-0001", tipo_seguimiento_pago=None,
        entregado=False, direccion_domicilio="Dirección anterior", paquetes_a_domicilio="OLD",
        paquetes_preparados=True, domicilio_coordinado=True)
    updates, preferences = [], []
    def update(_, **data):
        updates.append(data)
        for k, v in data.items():
            setattr(state, k, v)
    from app.services.delivery_cases import validar_datos, CAMPOS_CLIENTE
    env = {"telefono": "50700000000", "texto_cliente": "Lo quiero el martes",
        "historial": [], "CAMPOS_CLIENTE": CAMPOS_CLIENTE, "validar_datos": validar_datos,
        "service_block": lambda *a: None, "normalizar_codigo_cliente": lambda x: x.strip().upper(),
        "obtener_sesion_existente": lambda _: state, "actualizar_sesion": update,
        "consultar_facturas_por_codigo": lambda _: {"encontrado": True, "cantidad_facturas": 1,
            "saldo_pendiente_total": 0 if paid else 10, "facturas": [{"codigo": "FAC-TEST", "saldo_pendiente": 0 if paid else 10}]},
        "consultar_paquetes_por_codigo": lambda _: {"paquetes": [{"tracking": "NEW", "estado_cargo": "notificado"}]},
        "guardar_preferencias_cliente": lambda phone, pref: preferences.append((phone, pref))}
    exec(compile(module, "delivery-tool", "exec"), env)
    return env["_solicitar_entrega_domicilio"], state, updates, preferences


def test_tool_stores_requested_slot_without_confirming_and_resets_package_preparation(monkeypatch):
    fn, state, updates, preferences = tool(monkeypatch)
    result = fn("CBC-0001", "Dirección nueva", {"dia_solicitado": "martes", "horario_solicitado": "Antes de las 9"})
    assert result["solicitado"] and result["preferencias_guardadas"]
    assert preferences[0][1]["dia_solicitado"] == "martes"
    assert not state.domicilio_coordinado
    assert not state.paquetes_preparados
    assert all("fecha_confirmada" not in update for update in updates)
    assert "no prometas una cita" in result["mensaje"]


def test_tool_cannot_confirm_schedule_or_target_another_customer(monkeypatch):
    fn, state, updates, preferences = tool(monkeypatch)
    assert not fn("CBC-0001", "Address", {"fecha_confirmada": "2026-11-18"})["solicitado"]
    assert not fn("CBC-OTHER", "Address", {})["solicitado"]
    assert not updates and not preferences


def test_unpaid_case_keeps_payment_gate(monkeypatch):
    fn, state, updates, preferences = tool(monkeypatch, paid=False)
    result = fn("CBC-0001", "Address", {"dia_solicitado": "martes"})
    assert result["pago_pendiente"] and not result["solicitado"]
    assert not preferences
    assert not any("solicitud_domicilio_pendiente" in update for update in updates)
