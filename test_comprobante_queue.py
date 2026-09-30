"""Comprueba que ningún comprobante dependa de un retiro o domicilio."""

from datetime import datetime
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import panel
from app.tools.comprobantes import parsear_monto_comprobante


@pytest.mark.parametrize("accion", ["pago_no_recibido", "comprobante_incorrecto"])
def test_revision_guarda_nota_sin_confirmar_ni_registrar_pago(monkeypatch, accion):
    caso = _sesion(revisiones_comprobante_json=json.dumps([{"nota": "Anterior"}]))
    cambios = {}
    monkeypatch.setattr(panel, "obtener_sesion_existente", lambda telefono: caso)
    monkeypatch.setattr(panel, "actualizar_sesion", lambda telefono, **datos: cambios.update(datos))
    def no_registrar(*args, **kwargs):
        pytest.fail("Una revisión no debe modificar facturación")
    monkeypatch.setattr(panel, "registrar_pago_factura_desde_panel", no_registrar)
    resultado = panel.actualizar_estado_solicitud(caso.telefono, {
        "accion": accion, "tipo": "pago", "nota": "No aparece el ingreso",
        "comprobante_media_id": caso.comprobante_media_id,
    }, usuario="teresa")
    assert resultado["status"] == "ok"
    assert set(cambios) == {"revisiones_comprobante_json"}
    revisiones = json.loads(cambios["revisiones_comprobante_json"])
    assert revisiones[0]["nota"] == "Anterior"
    assert revisiones[-1]["usuario"] == "teresa"
    assert revisiones[-1]["accion"] == accion
    assert revisiones[-1]["comprobante_media_id"] == caso.comprobante_media_id
    assert caso.pago_confirmado is False


@pytest.mark.parametrize("nota,media,confirmado,codigo", [
    ("", "MEDIA-TEST", False, 400),
    ("x" * 1001, "MEDIA-TEST", False, 400),
    ("Revisado", "ANTERIOR", False, 409),
    ("Revisado", "MEDIA-TEST", True, 409),
])
def test_revision_invalida_no_se_guarda(monkeypatch, nota, media, confirmado, codigo):
    caso = _sesion(pago_confirmado=confirmado)
    monkeypatch.setattr(panel, "obtener_sesion_existente", lambda telefono: caso)
    monkeypatch.setattr(panel, "actualizar_sesion", lambda *a, **k: pytest.fail("No debe guardar"))
    with pytest.raises(HTTPException) as error:
        panel.actualizar_estado_solicitud(caso.telefono, {
            "accion": "pago_no_recibido", "tipo": "retiro", "nota": nota,
            "comprobante_media_id": media,
        }, usuario="teresa")
    assert error.value.status_code == codigo


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


def test_retiro_sin_cliente_verificado_indica_verificacion_y_bloquea_pago(monkeypatch):
    sesion = _sesion(
        codigo_cliente_verificado=None, entregado=False, aviso_retiro_pendiente=True
    )
    monkeypatch.setattr(panel, "listar_todas_sesiones", lambda limite=500: [sesion])
    monkeypatch.setattr(panel, "obtener_sesion_existente", lambda _telefono: sesion)

    caso = panel.listar_solicitudes(usuario="tester")[0]
    assert caso["requiere_verificacion"] is True
    assert caso["requiere_factura"] is False
    with pytest.raises(HTTPException) as error:
        panel.actualizar_estado_solicitud(
            sesion.telefono, {"tipo": "retiro", "accion": "confirmar_pago"}, usuario="tester"
        )
    assert error.value.status_code == 409
    assert sesion.pago_confirmado is False


def test_comprobante_solo_pago_sin_cliente_no_se_archiva(monkeypatch):
    sesion = _sesion(codigo_cliente_verificado=None)
    monkeypatch.setattr(panel, "listar_todas_sesiones", lambda limite=500: [sesion])
    monkeypatch.setattr(panel, "obtener_sesion_existente", lambda _telefono: sesion)

    caso = panel.listar_solicitudes(usuario="tester")[0]
    assert caso["tipo"] == "pago"
    assert caso["requiere_verificacion"] is True
    with pytest.raises(HTTPException) as error:
        panel.actualizar_estado_solicitud(
            sesion.telefono, {"tipo": "pago", "accion": "confirmar_pago"}, usuario="tester"
        )
    assert error.value.status_code == 409
    assert sesion.pago_confirmado is False


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
