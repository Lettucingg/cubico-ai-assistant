"""Comprueba que ningún comprobante dependa de un retiro o domicilio."""

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import panel
from app.tools.comprobantes import parsear_monto_comprobante


def _sesion(**cambios):
    datos = {
        "telefono": "11111111111",
        "codigo_cliente_verificado": "CBC-TEST",
        "entregado": True,
        "pago_reportado": True,
        "pago_confirmado": False,
        "aviso_retiro_pendiente": False,
        "solicitud_domicilio_pendiente": False,
        "paquetes_a_retirar": None,
        "paquetes_a_domicilio": None,
        "direccion_domicilio": None,
        "monto_pago_reportado": 10.0,
        "metodo_pago_reportado": "Yappy",
        "referencia_pago_reportado": "REF-TEST",
        "fecha_pago_reportado": "14/09/2026",
        "paquetes_preparados": False,
        "domicilio_coordinado": False,
        "comprobante_media_id": "MEDIA-TEST",
        "solicitud_actualizada_en": datetime(2026, 9, 14),
        "actualizado_en": datetime(2026, 9, 14),
    }
    datos.update(cambios)
    return SimpleNamespace(**datos)


def _facturas(_codigo):
    return {
        "encontrado": True,
        "cantidad_facturas": 1,
        "saldo_pendiente_total": 10.0,
        "facturas": [{
            "codigo": "FAC-TEST",
            "saldo_pendiente": 10.0,
            "paquetes": [{"tracking": "TRACK-TEST"}],
        }],
    }


def test_comprobante_sin_solicitud_crea_caso_de_pago(monkeypatch):
    monkeypatch.setattr(panel, "listar_todas_sesiones", lambda limite=500: [_sesion()])
    monkeypatch.setattr(panel, "consultar_facturas_por_codigo", _facturas)
    monkeypatch.setattr(panel, "_nombre_cliente", lambda sesion: "Cliente Prueba")

    solicitudes = panel.listar_solicitudes(usuario="tester")

    assert len(solicitudes) == 1
    assert solicitudes[0]["tipo"] == "pago"
    assert solicitudes[0]["tiene_comprobante"] is True
    assert solicitudes[0]["factura_sugerida"] == "FAC-TEST"


def test_comprobante_con_retiro_no_se_duplica(monkeypatch):
    caso = _sesion(entregado=False, aviso_retiro_pendiente=True)
    monkeypatch.setattr(panel, "listar_todas_sesiones", lambda limite=500: [caso])
    monkeypatch.setattr(panel, "consultar_facturas_por_codigo", _facturas)
    monkeypatch.setattr(panel, "_nombre_cliente", lambda sesion: "Cliente Prueba")

    solicitudes = panel.listar_solicitudes(usuario="tester")

    assert [solicitud["tipo"] for solicitud in solicitudes] == ["retiro"]


def test_comprobante_de_factura_ya_pagada_permite_preparar_retiro(monkeypatch):
    sesion = _sesion(entregado=False, aviso_retiro_pendiente=True)
    monkeypatch.setattr(panel, "obtener_sesion_existente", lambda _telefono: sesion)
    monkeypatch.setattr(panel, "consultar_facturas_por_codigo", lambda _codigo: {
        "encontrado": True, "cantidad_facturas": 1, "saldo_pendiente_total": 0,
        "facturas": [{"codigo": "FAC-TEST", "saldo_pendiente": 0}],
    })
    monkeypatch.setattr(panel, "registrar_pago_factura_desde_panel", lambda *_args: pytest.fail("Duplicó el pago"))
    monkeypatch.setattr(panel, "actualizar_sesion", lambda _telefono, **cambios: [setattr(sesion, k, v) for k, v in cambios.items()])

    respuesta = panel.actualizar_estado_solicitud(
        sesion.telefono, {"tipo": "retiro", "accion": "confirmar_pago"}, usuario="operador_prueba"
    )
    assert respuesta["pago"] is None
    assert sesion.pago_confirmado is True
    panel.actualizar_estado_solicitud(
        sesion.telefono, {"tipo": "retiro", "accion": "preparar"}, usuario="operador_prueba"
    )
    assert sesion.paquetes_preparados is True


def test_comprobante_de_factura_ya_pagada_permite_coordinar_domicilio(monkeypatch):
    sesion = _sesion(entregado=False, solicitud_domicilio_pendiente=True)
    monkeypatch.setattr(panel, "obtener_sesion_existente", lambda _telefono: sesion)
    monkeypatch.setattr(panel, "consultar_facturas_por_codigo", lambda _codigo: {
        "encontrado": True, "cantidad_facturas": 1, "saldo_pendiente_total": 0,
        "facturas": [{"codigo": "FAC-TEST", "saldo_pendiente": 0}],
    })
    monkeypatch.setattr(panel, "registrar_pago_factura_desde_panel", lambda *_args: pytest.fail("Duplicó el pago"))
    monkeypatch.setattr(panel, "actualizar_sesion", lambda _telefono, **cambios: [setattr(sesion, k, v) for k, v in cambios.items()])

    for accion in ("confirmar_pago", "preparar", "coordinar"):
        panel.actualizar_estado_solicitud(
            sesion.telefono, {"tipo": "domicilio", "accion": accion}, usuario="operador_prueba"
        )
    assert sesion.pago_confirmado is True
    assert sesion.paquetes_preparados is True
    assert sesion.domicilio_coordinado is True


def test_comprobante_sin_factura_no_se_marca_confirmado(monkeypatch):
    sesion = _sesion(entregado=False, aviso_retiro_pendiente=True)
    monkeypatch.setattr(panel, "obtener_sesion_existente", lambda _telefono: sesion)
    monkeypatch.setattr(panel, "consultar_facturas_por_codigo", lambda _codigo: {
        "encontrado": True, "cantidad_facturas": 0, "saldo_pendiente_total": 0, "facturas": [],
    })
    with pytest.raises(HTTPException) as error:
        panel.actualizar_estado_solicitud(
            sesion.telefono, {"tipo": "retiro", "accion": "confirmar_pago"}, usuario="operador_prueba"
        )
    assert error.value.status_code == 409


@pytest.mark.parametrize("texto,esperado", [
    ("USD 1,234.56", 1234.56), ("B/. 1.234,56", 1234.56),
    ("$10.00", 10.0), ("1,000", 1000.0),
    ("no visible", None), ("0.00", None),
])
def test_monto_del_comprobante_no_trunca_los_miles(texto, esperado):
    assert parsear_monto_comprobante(texto) == esperado
