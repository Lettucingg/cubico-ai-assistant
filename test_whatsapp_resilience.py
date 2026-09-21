"""Pruebas contra pérdida y duplicación de mensajes entrantes."""

import asyncio

import httpx
import pytest

from app.api import whatsapp


def _mensaje(tipo, texto=None, media_id=None, message_id="wamid-1", timestamp="1"):
    return {
        "telefono": "50760000000",
        "tipo": tipo,
        "texto": texto,
        "media_id": media_id,
        "message_id": message_id,
        "timestamp": timestamp,
    }


def test_combina_imagen_seguida_de_explicacion():
    imagen = _mensaje("image", media_id="media-1", message_id="imagen")
    texto = _mensaje("text", texto="¿Cuánto cuesta esta carga?", message_id="texto")

    combinado, pendiente = whatsapp.combinar_mensajes_para_buffer(imagen, texto)

    assert pendiente is None
    assert combinado["tipo"] == "image"
    assert combinado["media_id"] == "media-1"
    assert combinado["texto"] == "¿Cuánto cuesta esta carga?"
    assert combinado["message_id"] == "texto"


def test_combina_explicacion_seguida_de_imagen():
    texto = _mensaje("text", texto="Cotízame esto desde China", message_id="texto")
    imagen = _mensaje("image", media_id="media-1", message_id="imagen")

    combinado, pendiente = whatsapp.combinar_mensajes_para_buffer(texto, imagen)

    assert pendiente is None
    assert combinado["tipo"] == "image"
    assert combinado["media_id"] == "media-1"
    assert combinado["texto"] == "Cotízame esto desde China"


def test_dos_imagenes_no_descartan_la_primera():
    primera = _mensaje("image", media_id="media-1", message_id="imagen-1")
    segunda = _mensaje("image", media_id="media-2", message_id="imagen-2")

    combinado, pendiente = whatsapp.combinar_mensajes_para_buffer(primera, segunda)

    assert combinado["media_id"] == "media-2"
    assert pendiente["media_id"] == "media-1"


def test_ignora_reintento_del_mismo_wamid():
    whatsapp.mensajes_entrantes_recientes.clear()

    assert whatsapp.registrar_mensaje_entrante_una_vez("wamid-repetido", ahora=100)
    assert not whatsapp.registrar_mensaje_entrante_una_vez("wamid-repetido", ahora=101)


def test_permite_wamid_nuevo_y_limpia_el_vencido():
    whatsapp.mensajes_entrantes_recientes.clear()
    whatsapp.registrar_mensaje_entrante_una_vez("wamid-viejo", ahora=100)

    assert whatsapp.registrar_mensaje_entrante_una_vez("wamid-nuevo", ahora=3701)
    assert "wamid-viejo" not in whatsapp.mensajes_entrantes_recientes


def test_error_de_plantilla_muestra_causa_segura_de_meta(monkeypatch):
    class ClienteFalso:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return httpx.Response(
                404,
                json={
                    "error": {
                        "message": "Template name does not exist in the translation",
                        "code": 132001,
                        "error_data": {
                            "details": "template cubico_saludo does not exist in es"
                        },
                    }
                },
            )

    monkeypatch.setattr(whatsapp.httpx, "AsyncClient", lambda **kwargs: ClienteFalso())

    with pytest.raises(RuntimeError) as error:
        asyncio.run(
            whatsapp.enviar_plantilla_whatsapp(
                "50760000000", "cubico_saludo", [], idioma="es"
            )
        )

    texto = str(error.value)
    assert "código 132001" in texto
    assert "does not exist in es" in texto
    assert "WHATSAPP_TOKEN" not in texto
