"""Pruebas de memoria visual y cotizaciones de imágenes."""

from app.ai.orchestrator import normalizar_historial_para_claude
from app.tools.comprobantes import detectar_mime_imagen, interpretar_analisis_imagen
from app.tools.cotizador import calcular_costo_envio


def test_conserva_datos_visuales_para_siguientes_mensajes():
    analisis = interpretar_analisis_imagen(
        "ES_COMPROBANTE: no\n"
        "CONTEXTO_VISUAL: Tabla de 10 cajas; total 252 kg y 1.40035 CBM.\n"
        "===RESPUESTA===\nVeo el manifiesto."
    )

    assert analisis["contexto_visual"] == (
        "Tabla de 10 cajas; total 252 kg y 1.40035 CBM."
    )

    historial = [{
        "role": "user",
        "content": "[Cliente envió una imagen]",
        "contexto_ia": analisis["contexto_visual"],
    }]
    mensajes = normalizar_historial_para_claude(historial)

    assert "1.40035 CBM" in mensajes[0]["content"]
    assert "Cliente envió" not in mensajes[0]["content"]


def test_detecta_png_sin_confiar_en_extension():
    assert detectar_mime_imagen(b"\x89PNG\r\n\x1a\nresto") == "image/png"


def test_cotiza_china_maritimo_desde_cbm_total():
    resultado = calcular_costo_envio(
        "maritimo",
        origen="china",
        volumen_cbm=1.40035,
    )

    assert resultado["error"] is False
    assert resultado["volumen_cbm_facturable"] == 1.41
    assert resultado["costo_estimado"] == 458.25


def test_respeta_minimo_china_maritimo():
    resultado = calcular_costo_envio(
        "maritimo",
        origen="china",
        volumen_cbm=0.01,
    )

    assert resultado["costo_estimado"] == 45.00


def test_mantiene_tarifa_aerea_miami_existente():
    resultado = calcular_costo_envio("aereo", peso_libras=1.2)

    assert resultado["origen"] == "miami"
    assert resultado["peso_libras_redondeado"] == 2
    assert resultado["costo_estimado"] == 5.80


def test_china_aereo_usa_tarifa_china():
    resultado = calcular_costo_envio(
        "aereo",
        origen="china",
        peso_libras=1.2,
    )

    assert resultado["peso_libras_redondeado"] == 2
    assert resultado["costo_estimado"] == 24.00
