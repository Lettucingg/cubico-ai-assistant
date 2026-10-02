"""Pruebas para no confundir una caída del tracking con un paquete inexistente."""

import httpx
import pytest

from app.tools import ptyfreight


def _respuesta(codigo: int, datos=None):
    solicitud = httpx.Request("GET", "http://tracking.local/prueba")
    return httpx.Response(codigo, request=solicitud, json=datos)


def test_timeout_se_marca_como_servicio_indisponible(monkeypatch):
    ptyfreight._cache_tracking.clear()

    def fallar(_url, timeout):
        raise httpx.ConnectTimeout("timeout", request=httpx.Request("GET", _url))

    monkeypatch.setattr(ptyfreight.httpx, "get", fallar)

    resultado = ptyfreight.consultar_tracking("TRACK-1")

    assert resultado["error"] is True
    assert resultado["fuente"] == "servicio_indisponible"
    assert "TRACK-1" not in ptyfreight._cache_tracking


def test_error_500_no_se_reporta_como_no_encontrado(monkeypatch):
    ptyfreight._cache_tracking.clear()
    monkeypatch.setattr(
        ptyfreight.httpx,
        "get",
        lambda _url, timeout: _respuesta(500, {"error": "temporal"}),
    )

    resultado = ptyfreight.consultar_tracking("TRACK-2")

    assert resultado["fuente"] == "servicio_indisponible"
    assert resultado["codigo_http"] == 500


def test_404_si_es_no_encontrado_y_se_puede_cachear(monkeypatch):
    ptyfreight._cache_tracking.clear()
    monkeypatch.setattr(
        ptyfreight.httpx,
        "get",
        lambda _url, timeout: _respuesta(404, {"detalle": "no encontrado"}),
    )

    resultado = ptyfreight.consultar_tracking("TRACK-3")

    assert resultado["fuente"] == "no_encontrado"
    assert resultado.get("error") is not True
    assert "TRACK-3" in ptyfreight._cache_tracking


def test_json_invalido_se_marca_como_fallo_temporal(monkeypatch):
    ptyfreight._cache_tracking.clear()
    solicitud = httpx.Request("GET", "http://tracking.local/prueba")
    respuesta = httpx.Response(200, request=solicitud, content=b"no-es-json")
    monkeypatch.setattr(ptyfreight.httpx, "get", lambda _url, timeout: respuesta)

    resultado = ptyfreight.consultar_tracking("TRACK-4")

    assert resultado["tipo_error"] == "respuesta_invalida"
    assert resultado["fuente"] == "servicio_indisponible"


def test_fuente_desconocida_no_se_convierte_en_no_encontrado():
    resultado = ptyfreight._mapear_respuesta({"fuente": "proveedor_nuevo"})

    assert resultado["error"] is True
    assert resultado["tipo_error"] == "fuente_desconocida"


def test_resultado_explicito_no_encontrado():
    resultado = ptyfreight._mapear_respuesta({"fuente": "no_encontrado"})

    assert resultado["fuente"] == "no_encontrado"
    assert resultado.get("error") is not True


def _respuesta_pty_publica():
    # Formato observado en producción: fuente pty y registros anidados.
    return {
        "fuente": "pty",
        "tracking": "TRACK-PTY",
        "pty": {
            "status": "ok",
            "tracking_number": "TRACK-PTY",
            "tipo": "aereo",
            "packages": [
                {
                    "ware_house": "10", "state": 0,
                    "date_of_admission": "2026-09-21T08:59:46-05:00",
                    "is_unknown": False, "is_processed": True,
                },
                {
                    "ware_house": "SACO 162 MALID", "state": 0,
                    "date_of_admission": "2026-09-23T14:19:00-05:00",
                    "is_unknown": True, "is_processed": False,
                },
            ],
        },
    }


def test_formato_pty_publico_se_lee_y_cachea_sin_inventar_entrega(monkeypatch):
    ptyfreight._cache_tracking.clear()
    llamadas = []

    def consultar(url, timeout):
        llamadas.append(url)
        return _respuesta(200, _respuesta_pty_publica())

    monkeypatch.setattr(ptyfreight.httpx, "get", consultar)
    resultado = ptyfreight.consultar_tracking("TRACK-PTY")

    assert resultado["encontrado"] is True
    assert resultado["fuente"] == "ptyfreight"
    assert resultado.get("error") is not True
    assert resultado["estado"] == "Recibido en Miami"
    assert "PTY" not in resultado["estado"]
    assert resultado["registros_proveedor"] == [
        {"estado": "Recibido en Miami", "fecha_ingreso_proveedor": "2026-09-21T08:59:46-05:00", "procesado_por_proveedor": True},
        {"identificacion_incorrecta": True, "estado": "Recibido en Miami", "fecha_ingreso_proveedor": "2026-09-23T14:19:00-05:00", "procesado_por_proveedor": False},
    ]
    assert resultado["ubicacion"] == "Miami"
    assert resultado["disponibilidad_local_confirmada"] is False
    assert resultado["entrega_cliente_confirmada"] is False
    assert ptyfreight.consultar_tracking("TRACK-PTY") == resultado
    assert len(llamadas) == 1
    assert resultado["identificacion_incorrecta"] is True
    assert resultado["requiere_revision_humana"] is True
    assert "mal identificado" in resultado["advertencia_cliente"]


def test_formato_ptyfreight_anterior_se_conserva():
    resultado = ptyfreight._mapear_respuesta({
        "fuente": "ptyfreight", "estado_texto": "En tránsito", "ubicacion": "Miami",
    })
    assert resultado == {
        "encontrado": True, "fuente": "ptyfreight", "estado": "En tránsito", "ubicacion": "Miami",
    }


@pytest.mark.parametrize("datos", [
    [], None, {"fuente": "pty"},
    {"fuente": "pty", "pty": {"status": "error", "packages": [{}]}},
    {"fuente": "pty", "pty": {"status": "ok", "packages": []}},
    {"fuente": "pty", "pty": {"status": "ok", "packages": [None]}},
    {"fuente": "pty", "pty": {"status": "ok", "packages": [{}]}},
])
def test_respuestas_incompletas_no_son_paquete_inexistente(datos):
    resultado = ptyfreight._mapear_respuesta(datos)
    assert resultado["fuente"] == "servicio_indisponible"
    assert resultado["error"] is True


def test_error_de_formato_no_se_cachea_y_permite_recuperacion(monkeypatch):
    ptyfreight._cache_tracking.clear()
    respuestas = iter([{"fuente": "proveedor_nuevo"}, _respuesta_pty_publica()])
    monkeypatch.setattr(ptyfreight.httpx, "get", lambda url, timeout: _respuesta(200, next(respuestas)))
    assert ptyfreight.consultar_tracking("TRACK-PTY")["error"] is True
    assert "TRACK-PTY" not in ptyfreight._cache_tracking
    assert ptyfreight.consultar_tracking("TRACK-PTY")["encontrado"] is True


@pytest.mark.parametrize("state", [0, "0"])
def test_estado_cero_coincide_con_la_pagina_de_cubico(state):
    resultado = ptyfreight._mapear_respuesta({
        "fuente": "pty", "pty": {"status": "ok", "packages": [{"state": state}]},
    })
    assert resultado["encontrado"] is True
    assert resultado["estado"] == "Recibido en Miami"
    assert resultado["ubicacion"] == "Miami"


@pytest.mark.parametrize("state", [1, 2, 3, 4])
def test_otros_estados_no_inventan_panama_retiro_ni_entrega(state):
    resultado = ptyfreight._mapear_respuesta({
        "fuente": "pty", "pty": {"status": "ok", "packages": [{"state": state}]},
    })
    assert resultado["encontrado"] is True
    assert "ubicacion" not in resultado
    assert resultado["disponibilidad_local_confirmada"] is False
    assert resultado["entrega_cliente_confirmada"] is False
    assert "PTY" not in resultado["estado"]
    if state in (3, 4):
        assert "sin confirmar" in resultado["estado"]


@pytest.mark.parametrize("state", [False, True, None, 99, "99", 0.0])
def test_estado_desconocido_no_se_convierte_en_miami(state):
    datos = _respuesta_pty_publica()
    for registro in datos["pty"]["packages"]:
        registro["state"] = state
    resultado = ptyfreight._mapear_respuesta(datos)
    assert resultado["encontrado"] is True
    assert "ubicacion" not in resultado
    assert "pendiente de confirmar" in resultado["estado"]


def test_registros_discordantes_no_eligen_una_ubicacion_sin_confirmar():
    datos = _respuesta_pty_publica()
    datos["pty"]["packages"][1]["state"] = 2
    resultado = ptyfreight._mapear_respuesta(datos)
    assert "ubicacion" not in resultado
    assert "pendiente de confirmar" in resultado["estado"]
    assert [r["estado"] for r in resultado["registros_proveedor"]] == [
        "Recibido en Miami", "En tránsito",
    ]


@pytest.mark.parametrize("campo", ["ware_house", "warehouse_number"])
@pytest.mark.parametrize("valor", ["SACO 162 MALID", "malid", "SACO_malid", "MALID-162"])
def test_malid_advierta_sin_ocultar_miami(campo, valor):
    resultado = ptyfreight._mapear_respuesta({
        "fuente": "pty", "pty": {"status": "ok", "packages": [{"state": 0, campo: valor}]},
    })
    assert resultado["ubicacion"] == "Miami"
    assert resultado["requiere_revision_humana"] is True
    assert "mal identificado" in resultado["advertencia_cliente"]
    assert "PTY" not in resultado["advertencia_cliente"]
    assert "MALID" not in resultado["advertencia_cliente"]


@pytest.mark.parametrize("valor", ["10", "SACO 162", "NORMALID", None, 10])
def test_bodega_sin_malid_no_marca_identificacion_incorrecta(valor):
    resultado = ptyfreight._mapear_respuesta({
        "fuente": "pty", "pty": {"status": "ok", "packages": [
            {"state": 0, "ware_house": valor, "is_unknown": True},
        ]},
    })
    assert "identificacion_incorrecta" not in resultado
    assert "advertencia_cliente" not in resultado
    assert "requiere_revision_humana" not in resultado
