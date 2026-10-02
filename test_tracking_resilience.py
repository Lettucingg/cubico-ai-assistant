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
    assert "entrega al cliente no confirmadas" in resultado["estado"]
    assert "PTY" not in resultado["estado"]
    assert resultado["registros_proveedor"] == [
        {"fecha_ingreso_proveedor": "2026-09-21T08:59:46-05:00", "procesado_por_proveedor": True},
        {"fecha_ingreso_proveedor": "2026-09-23T14:19:00-05:00", "procesado_por_proveedor": False},
    ]
    assert "ubicacion" not in resultado
    assert ptyfreight.consultar_tracking("TRACK-PTY") == resultado
    assert len(llamadas) == 1


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
