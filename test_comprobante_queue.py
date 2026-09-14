"""Comprueba que ningún comprobante dependa de un retiro o domicilio."""

from datetime import datetime
from types import SimpleNamespace

from app.api import panel


def _sesion(**cambios):
    datos = {
        "telefono": "50760000000",
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
