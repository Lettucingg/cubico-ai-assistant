"""Pruebas de los bloqueos operativos del panel."""

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import panel
from app.main import app


def _sesion(codigo="CBC-TEST", **cambios):
    datos = {
        "telefono": "50760000000",
        "codigo_cliente_verificado": codigo,
        "pago_confirmado": False,
        "paquetes_preparados": False,
        "domicilio_coordinado": False,
        "aviso_retiro_pendiente": False,
        "solicitud_domicilio_pendiente": True,
    }
    datos.update(cambios)
    return SimpleNamespace(**datos)


def test_bloquea_entrega_sin_factura(monkeypatch):
    monkeypatch.setattr(
        panel,
        "consultar_facturas_por_codigo",
        lambda _codigo: {
            "encontrado": True,
            "cantidad_facturas": 0,
            "saldo_pendiente_total": 0,
            "facturas": [],
        },
    )

    with pytest.raises(HTTPException) as error:
        panel._exigir_factura_pagada(_sesion())

    assert error.value.status_code == 409
    assert "factura asociada" in error.value.detail


def test_bloquea_entrega_con_saldo(monkeypatch):
    monkeypatch.setattr(
        panel,
        "consultar_facturas_por_codigo",
        lambda _codigo: {
            "encontrado": True,
            "cantidad_facturas": 1,
            "saldo_pendiente_total": 10,
            "facturas": [{"codigo": "FAC-TEST", "saldo_pendiente": 10}],
        },
    )

    with pytest.raises(HTTPException) as error:
        panel._exigir_factura_pagada(_sesion())

    assert error.value.status_code == 409
    assert "saldo pendiente" in error.value.detail


def test_permite_entrega_con_factura_pagada(monkeypatch):
    esperado = {
        "encontrado": True,
        "cantidad_facturas": 1,
        "saldo_pendiente_total": 0,
        "facturas": [{"codigo": "FAC-TEST", "saldo_pendiente": 0}],
    }
    monkeypatch.setattr(panel, "consultar_facturas_por_codigo", lambda _codigo: esperado)

    assert panel._exigir_factura_pagada(_sesion()) == esperado


def test_modo_humano_guarda_operador(monkeypatch):
    cambios = {}
    monkeypatch.setattr(panel, "obtener_sesion_existente", lambda _telefono: _sesion())
    monkeypatch.setattr(panel, "actualizar_sesion", lambda _telefono, **datos: cambios.update(datos))

    respuesta = asyncio.run(
        panel.tomar_control(
            "50760000000",
            {"accion": "tomar"},
            usuario="alexander",
        )
    )

    assert respuesta["control"] is True
    assert respuesta["operador"] == "alexander"
    assert cambios["atencion_humana_directa"] is True
    assert cambios["atencion_humana_por"] == "alexander"
    assert cambios["atencion_humana_desde"] is not None


def test_rechaza_accion_de_control_desconocida(monkeypatch):
    monkeypatch.setattr(panel, "obtener_sesion_existente", lambda _telefono: _sesion())

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            panel.tomar_control(
                "50760000000",
                {"accion": "inventada"},
                usuario="alexander",
            )
        )

    assert error.value.status_code == 400


def test_no_permite_robar_control_sin_confirmacion(monkeypatch):
    monkeypatch.setattr(
        panel,
        "obtener_sesion_existente",
        lambda _telefono: _sesion(
            atencion_humana_directa=True,
            atencion_humana_por="luis",
        ),
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            panel.tomar_control(
                "50760000000",
                {"accion": "tomar"},
                usuario="alexander",
            )
        )

    assert error.value.status_code == 409
    assert "luis" in error.value.detail


def test_transferencia_confirmada_cambia_operador(monkeypatch):
    cambios = {}
    monkeypatch.setattr(
        panel,
        "obtener_sesion_existente",
        lambda _telefono: _sesion(
            atencion_humana_directa=True,
            atencion_humana_por="luis",
        ),
    )
    monkeypatch.setattr(panel, "actualizar_sesion", lambda _telefono, **datos: cambios.update(datos))

    respuesta = asyncio.run(
        panel.tomar_control(
            "50760000000",
            {"accion": "tomar", "forzar": True},
            usuario="alexander",
        )
    )

    assert respuesta["operador"] == "alexander"
    assert cambios["atencion_humana_por"] == "alexander"


def test_solo_dueno_puede_devolver_a_bruno(monkeypatch):
    monkeypatch.setattr(
        panel,
        "obtener_sesion_existente",
        lambda _telefono: _sesion(
            atencion_humana_directa=True,
            atencion_humana_por="luis",
        ),
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            panel.tomar_control(
                "50760000000",
                {"accion": "devolver"},
                usuario="alexander",
            )
        )

    assert error.value.status_code == 409
    assert "luis" in error.value.detail


def test_bloquea_respuesta_de_otro_operador(monkeypatch):
    monkeypatch.setattr(
        panel,
        "obtener_sesion_existente",
        lambda _telefono: _sesion(
            atencion_humana_directa=True,
            atencion_humana_por="luis",
        ),
    )

    with pytest.raises(HTTPException) as error:
        panel._validar_operador_conversacion("50760000000", "alexander")

    assert error.value.status_code == 409
    assert "luis" in error.value.detail


def test_envio_directo_exige_ser_dueno(monkeypatch):
    monkeypatch.setattr(
        panel,
        "obtener_sesion_existente",
        lambda _telefono: _sesion(
            atencion_humana_directa=False,
            atencion_humana_por=None,
        ),
    )

    with pytest.raises(HTTPException) as error:
        panel._validar_operador_conversacion(
            "50760000000",
            "alexander",
            requiere_control=True,
        )

    assert error.value.status_code == 409
    assert "tomar el control" in error.value.detail


def test_endpoint_liviano_detecta_ultimo_mensaje_cliente(monkeypatch):
    fecha = datetime(2026, 9, 14, 10, 0, 0)
    caso = SimpleNamespace(
        telefono="50760000000",
        actualizado_en=fecha,
        necesita_atencion_humana=False,
        motivo_escalamiento=None,
        atencion_humana_directa=True,
        atencion_humana_por="alexander",
        atencion_humana_desde=fecha,
        ultimo_leido_panel=None,
        obtener_historial=lambda: [{
            "role": "user",
            "content": "Hola",
            "timestamp": "2026-09-14T10:00:00.123Z",
            "whatsapp_message_id": "wamid-1",
        }],
    )
    monkeypatch.setattr(panel, "listar_todas_sesiones", lambda limite=100: [caso])

    resultado = panel.listar_actividad_panel(usuario="alexander")

    assert "/panel/actividad" in app.openapi()["paths"]
    assert resultado[0]["ultimo_mensaje_cliente"]["id"] == "wamid-1"
    assert resultado[0]["tiene_no_leidos"] is True
