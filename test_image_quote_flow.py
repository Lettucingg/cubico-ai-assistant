"""Pruebas de memoria visual y cotizaciones de imágenes."""

from types import SimpleNamespace

from app.ai import orchestrator
from app.ai.orchestrator import normalizar_historial_para_claude
from app.tools import comprobantes
from app.tools.comprobantes import (
    analizar_imagen_cliente,
    detectar_mime_imagen,
    interpretar_analisis_imagen,
)
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


def test_acepta_separador_con_espacios():
    resultado = interpretar_analisis_imagen(
        "ES_COMPROBANTE: no\n"
        "CONTEXTO_VISUAL: Total 1.40035 CBM.\n"
        "=== RESPUESTA ===\nVeo el total del manifiesto."
    )

    assert resultado["formato_valido"] is True
    assert resultado["contexto_visual"] == "Total 1.40035 CBM."


def test_reintenta_tabla_si_claude_omite_formato(monkeypatch):
    respuestas = iter([
        SimpleNamespace(
            content=[SimpleNamespace(type="text", text="Veo una tabla de carga.")],
            usage=None,
        ),
        SimpleNamespace(
            content=[SimpleNamespace(
                type="text",
                text=(
                    "ES_COMPROBANTE: no\n"
                    "CONTEXTO_VISUAL: Tabla con total 156.5 kg, 252 kg "
                    "cobrables y 1.40035 CBM.\n"
                    "===RESPUESTA===\nVeo los totales del manifiesto."
                ),
            )],
            usage=None,
        ),
    ])
    instrucciones_recibidas = []

    def crear_respuesta(**argumentos):
        instrucciones_recibidas.append(
            argumentos["messages"][0]["content"][1]["text"]
        )
        return next(respuestas)

    monkeypatch.setattr(
        comprobantes.cliente_claude.messages,
        "create",
        crear_respuesta,
    )

    resultado = analizar_imagen_cliente(b"\xff\xd8imagen")

    assert len(instrucciones_recibidas) == 2
    assert "última fila" in instrucciones_recibidas[1]
    assert resultado["formato_valido"] is True
    assert "1.40035 CBM" in resultado["contexto_visual"]


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


def test_respuesta_fija_da_solo_la_tarifa_preguntada():
    respuesta = orchestrator.buscar_respuesta_fija("¿Cuánto cobran la libra?")

    assert respuesta == "Desde Miami por aéreo son $2.90 por libra."
    assert "China" not in respuesta


def test_tarifa_china_maritima_es_directa():
    respuesta = orchestrator.buscar_respuesta_fija(
        "¿Cuál es la tarifa marítima desde China por CBM?"
    )

    assert respuesta == "Desde China por marítimo son $325 por CBM, con un mínimo de $45."


def test_cantidad_cbm_no_es_interceptada_por_respuesta_fija():
    respuesta = orchestrator.buscar_respuesta_fija(
        "Tengo una carga desde China de 0.78342 CBM. "
        "¿Cuánto me cuesta traerla por marítimo?"
    )

    assert respuesta is None


def test_peso_china_no_es_interceptado_por_respuesta_fija():
    respuesta = orchestrator.buscar_respuesta_fija(
        "¿Cuánto cuesta traer 3.2 libras desde China por aéreo?"
    )

    assert respuesta is None


def test_consulta_ambigua_usa_contexto_de_claude():
    assert orchestrator.buscar_respuesta_fija("¿Cuánto cuesta el envío?") is None


def test_direccion_fija_no_muestra_variables_internas(monkeypatch):
    monkeypatch.setattr(orchestrator, "CUBICO_MIAMI_STREET", "123 Calle Prueba")
    monkeypatch.setattr(orchestrator, "CUBICO_MIAMI_CITY_ZIP", "Miami, FL 00000")
    monkeypatch.setattr(orchestrator, "CUBICO_MIAMI_PHONE", "000-0000")

    respuesta = orchestrator.buscar_respuesta_fija("¿Cuál es la dirección en Miami?")

    assert "123 Calle Prueba" in respuesta
    assert "{CUBICO_" not in respuesta


def test_fallo_repetido_no_repite_el_mismo_mensaje(monkeypatch):
    estado = SimpleNamespace(
        necesita_atencion_humana=False,
        motivo_escalamiento=None,
    )

    def actualizar(_telefono, **cambios):
        for clave, valor in cambios.items():
            setattr(estado, clave, valor)

    monkeypatch.setattr(orchestrator, "obtener_sesion_existente", lambda _telefono: estado)
    monkeypatch.setattr(orchestrator, "actualizar_sesion", actualizar)

    primera = orchestrator._escalar_fallo_de_respuesta("50760000000")
    segunda = orchestrator._escalar_fallo_de_respuesta("50760000000")

    assert primera == "Voy a pasarle esto al equipo para que lo revisen bien."
    assert segunda != primera
    assert "ya tiene" in segunda
