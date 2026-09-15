"""Pruebas para no confundir una caída del tracking con un paquete inexistente."""

import httpx

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
