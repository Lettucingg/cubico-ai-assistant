import base64

import httpx
from anthropic import Anthropic

from app.core.config import settings
from app.ai.orchestrator import SYSTEM_PROMPT
from app.db.session_store import registrar_uso_ia

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
        respuesta_info.raise_for_status()
        url_descarga = respuesta_info.json()["url"]
        respuesta_imagen = await client.get(url_descarga, headers=headers)
        respuesta_imagen.raise_for_status()
        if not respuesta_imagen.content:
            raise ValueError("Meta devolvió un comprobante vacío")
        if not respuesta_imagen.headers.get("content-type", "").lower().startswith("image/"):
            raise ValueError("Meta no devolvió una imagen válida")
        return respuesta_imagen.content


def analizar_imagen_cliente(
    imagen_bytes: bytes,
    texto_cliente: str | None = None,
    telefono: str | None = None,
) -> dict:
    """
    Analiza en una sola llamada a Claude una imagen enviada por un
    cliente: determina si es un comprobante de pago y, si lo es,
    extrae sus datos; si no lo es, genera directamente la respuesta
    natural que Bruno le da al cliente sobre lo que ve, considerando
    también el texto que haya escrito junto con la imagen.

    Evita la doble llamada (una para clasificar, otra para responder)
    que se hacía antes.
    """
    imagen_base64 = base64.b64encode(imagen_bytes).decode("utf-8")

    if texto_cliente:
        contexto_texto = f'junto con este mensaje: "{texto_cliente}"'
    else:
        contexto_texto = "sin ningún mensaje de texto adicional"

    instrucciones = f"""
Un cliente de Cúbico te mandó esta imagen por WhatsApp, {contexto_texto}.

Primero decide si es un comprobante de pago (transferencia, Yappy, o similar).

Si SÍ es un comprobante de pago, responde EXACTAMENTE en este formato:

ES_COMPROBANTE: si
MONTO: [monto si es visible, o "no visible"]
FECHA: [fecha si es visible, o "no visible"]
REFERENCIA: [número de referencia si es visible, o "no visible"]
METODO: [Yappy, transferencia, u otro si se puede identificar]
===RESPUESTA===
[el mensaje que le confirmarías al cliente que recibiste su comprobante, con tu tono normal]

Si NO es un comprobante de pago, responde EXACTAMENTE en este formato:

ES_COMPROBANTE: no
===RESPUESTA===
[tu respuesta natural sobre lo que ves en la imagen, tomando en cuenta el mensaje del cliente si mandó uno. Si es una captura de una tienda o de algo donde te está pidiendo ayuda, ayúdalo directamente con eso. Si no tiene nada que ver con Cúbico, dile con naturalidad qué ves y pregúntale en qué le puedes ayudar.]

No escribas nada antes de "ES_COMPROBANTE:" ni nada después del texto de la sección RESPUESTA. Esa sección debe quedar lista para mandarse tal cual al cliente por WhatsApp.
"""

    respuesta = cliente_claude.messages.create(
        model="claude-sonnet-5",
        max_tokens=500,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
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
                    "text": instrucciones,
                },
            ],
        }],
    )

    if telefono and getattr(respuesta, "usage", None) is not None:
        try:
            registrar_uso_ia(
                telefono=telefono,
                modelo=getattr(respuesta, "model", "claude-sonnet-5"),
                input_tokens=int(getattr(respuesta.usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(respuesta.usage, "output_tokens", 0) or 0),
            )
        except Exception as error:
            print(f"[WARN] No se pudo registrar uso de IA de imagen: {error}")

    texto_completo = "\n".join(
        bloque.text for bloque in respuesta.content if bloque.type == "text"
    ).strip()

    encabezado, separador, texto_para_cliente = texto_completo.partition("===RESPUESTA===")
    es_comprobante = "es_comprobante: si" in encabezado.lower()

    return {
        "es_comprobante": es_comprobante,
        "detalle_completo": encabezado.strip() if es_comprobante else None,
        "texto_respuesta": (
            texto_para_cliente.strip()
            if separador
            else "No pude ver bien la imagen. Cuéntame qué producto es y te calculo el costo de traerlo sin problema."
        ),
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
