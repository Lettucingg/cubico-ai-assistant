"""Control de emergencia desde el panel sin saltarse las reglas de negocio."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import panel


def _sesion(**cambios):
    datos = {
        "codigo_cliente_verificado": None,
        "tipo_cliente_verificado": None,
        "aviso_retiro_pendiente": False,
        "solicitud_domicilio_pendiente": False,
        "pago_reportado": False,
        "pago_confirmado": False,
    }
    datos.update(cambios)
    return SimpleNamespace(**datos)


def test_operador_puede_verificar_codigo_real_sin_correo(monkeypatch):
    cambios = {}
    monkeypatch.setattr(panel, "obtener_sesion_existente", lambda _telefono: _sesion())
    monkeypatch.setattr(
        panel,
        "obtener_nombre_completo_cliente",
        lambda _codigo: {
            "encontrado": True,
            "codigo_cliente": "AGENCIA-12",
            "tipo_cliente": "agencia",
            "nombre_completo": "Agencia Prueba",
        },
    )
    monkeypatch.setattr(
        panel,
        "actualizar_sesion",
        lambda telefono, **valores: cambios.update(telefono=telefono, **valores),
    )

    resultado = panel.control_operativo_manual(
        "50760000000",
        {"accion": "verificar", "codigo": "agencia-12"},
        usuario="alexander",
    )

    assert resultado["codigo"] == "AGENCIA-12"
    assert resultado["tipo_cliente"] == "agencia"
    assert cambios["estado"] == "verificado"
    assert cambios["codigo_cliente_verificado"] == "AGENCIA-12"


def test_verificacion_manual_rechaza_codigo_que_no_existe(monkeypatch):
    monkeypatch.setattr(panel, "obtener_sesion_existente", lambda _telefono: _sesion())
    monkeypatch.setattr(
        panel,
        "obtener_nombre_completo_cliente",
        lambda _codigo: {"encontrado": False},
    )

    with pytest.raises(HTTPException) as error:
        panel.control_operativo_manual(
            "50760000000",
            {"accion": "verificar", "codigo": "INVENTADO"},
            usuario="alexander",
        )

    assert error.value.status_code == 404


def test_operador_crea_domicilio_pendiente_sin_marcarlo_coordinado(monkeypatch):
    cambios = {}
    monkeypatch.setattr(
        panel,
        "obtener_sesion_existente",
        lambda _telefono: _sesion(codigo_cliente_verificado="CBC-0040"),
    )
    monkeypatch.setattr(
        panel,
        "consultar_paquetes_por_codigo",
        lambda _codigo: {
            "encontrado": True,
            "paquetes": [
                {"tracking": "TRACK-1", "estado_cargo": "notificado"},
                {"tracking": "TRACK-2", "estado_cargo": "recibido"},
            ],
        },
    )
    monkeypatch.setattr(
        panel,
        "actualizar_sesion",
        lambda telefono, **valores: cambios.update(telefono=telefono, **valores),
    )

    resultado = panel.control_operativo_manual(
        "50760000000",
        {"accion": "crear_domicilio", "direccion": "Calle 50, local 2"},
        usuario="alexander",
    )

    assert resultado["tipo"] == "domicilio"
    assert cambios["solicitud_domicilio_pendiente"] is True
    assert cambios["domicilio_coordinado"] is False
    assert cambios["paquetes_a_domicilio"] == "TRACK-1"
    assert cambios["direccion_domicilio"] == "Calle 50, local 2"


def test_pago_manual_entra_a_revision_sin_inventar_comprobante(monkeypatch):
    cambios = {}
    monkeypatch.setattr(
        panel,
        "obtener_sesion_existente",
        lambda _telefono: _sesion(codigo_cliente_verificado="CBC-0040"),
    )
    monkeypatch.setattr(
        panel,
        "actualizar_sesion",
        lambda telefono, **valores: cambios.update(telefono=telefono, **valores),
    )

    panel.control_operativo_manual(
        "50760000000",
        {"accion": "pago_por_comprobar", "monto": "6.00", "metodo": "Yappy"},
        usuario="alexander",
    )

    assert cambios["pago_reportado"] is True
    assert cambios["pago_confirmado"] is False
    assert cambios["monto_pago_reportado"] == 6.0
    assert "comprobante_media_id" not in cambios


def test_panel_expone_controles_manuales_sin_saturar_cabecera():
    html = open("app/static/panel-nuevo-diseno.html", encoding="utf-8").read()
    assert 'id="manual-verify"' in html
    assert 'id="manual-pickup"' in html
    assert 'id="manual-delivery"' in html
    assert 'id="manual-payment"' in html
    assert "Acciones manuales" in html
