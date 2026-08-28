import base64

import httpx
from anthropic import Anthropic

from app.core.config import settings

cliente_claude = Anthropic(api_key=settings.ANTHROPIC_API_KEY)


async def descargar_imagen_de_whatsapp(media_id: str) -> bytes:
    """
    Descarga una imagen real desde los servidores de Meta, usando
    el mismo patron de dos pasos que ya usamos para audio.
    """
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        respuesta_info = await client.get(
            f"https://graph.facebook.com/v21.0/{media_id}",
            headers=headers,
        )
        url_descarga = respuesta_info.json()["url"]
        respuesta_imagen = await client.get(url_descarga, headers=headers)
        return respuesta_imagen.content


def analizar_comprobante(imagen_bytes: bytes) -> dict:
    """
    Usa Claude (que sí puede ver imagenes) para analizar si la imagen
    es un comprobante de pago, y si lo es, extraer los datos visibles.
    """
    imagen_base64 = base64.b64encode(imagen_bytes).decode("utf-8")

    respuesta = cliente_claude.messages.create(
        model="claude-sonnet-5",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": imagen_base64,
                    },
                },
                {
                    "type": "text",
                    "text": (
                        "Analiza esta imagen. ¿Es un comprobante de pago "
                        "(como una transferencia, Yappy, o similar)? "
                        "Si lo es, responde EXACTAMENTE en este formato:\n"
                        "ES_COMPROBANTE: si\n"
                        "MONTO: [monto si es visible, o 'no visible']\n"
                        "FECHA: [fecha si es visible, o 'no visible']\n"
                        "REFERENCIA: [numero de referencia si es visible, o 'no visible']\n"
                        "METODO: [Yappy, transferencia, u otro si se puede identificar]\n\n"
                        "Si NO es un comprobante de pago, responde solo:\n"
                        "ES_COMPROBANTE: no"
                    ),
                },
            ],
        }],
    )

    texto_respuesta = respuesta.content[0].text
    es_comprobante = "es_comprobante: si" in texto_respuesta.lower()

    return {
        "es_comprobante": es_comprobante,
        "detalle_completo": texto_respuesta,
    }


def extraer_campos_comprobante(detalle_completo: str) -> dict:
    """
    Parsea los campos MONTO/FECHA/REFERENCIA/METODO del texto que
    devuelve analizar_comprobante, para mostrarlos por separado en la
    notificación al equipo.
    """
    campos = {
        "monto": "No especificado",
        "fecha": "No especificado",
        "referencia": "No especificado",
        "metodo": "No especificado",
    }
    prefijos = {"MONTO": "monto", "FECHA": "fecha", "REFERENCIA": "referencia", "METODO": "metodo"}

    for linea in detalle_completo.splitlines():
        prefijo, separador, valor = linea.partition(":")
        if not separador:
            continue
        clave = prefijos.get(prefijo.strip().upper())
        if clave:
            campos[clave] = valor.strip() or "No especificado"

    return campos
