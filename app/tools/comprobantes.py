import base64
import re

import httpx
from anthropic import Anthropic

from app.core.config import settings
from app.ai.orchestrator import SYSTEM_PROMPT
from app.db.session_store import registrar_uso_ia

cliente_claude = Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def detectar_mime_imagen(imagen_bytes: bytes) -> str:
    """Detecta los formatos de imagen admitidos por Claude sin confiar en la extensión."""
    if imagen_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if imagen_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if imagen_bytes.startswith(b"RIFF") and imagen_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def interpretar_analisis_imagen(texto_completo: str) -> dict:
    """Convierte la salida estructurada del análisis en datos seguros para el flujo."""
    partes = re.split(
        r"={2,}\s*RESPUESTA\s*={2,}",
        texto_completo,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    encabezado = partes[0]
    separador = len(partes) == 2
    texto_para_cliente = partes[1] if separador else ""
    es_comprobante = "es_comprobante: si" in encabezado.lower()
    contexto_visual = None
    if not es_comprobante:
        marcador = "CONTEXTO_VISUAL:"
        posicion = encabezado.upper().find(marcador)
        if posicion >= 0:
            contexto_visual = encabezado[posicion + len(marcador):].strip()
    return {
        "es_comprobante": es_comprobante,
        "detalle_completo": encabezado.strip() if es_comprobante else None,
        "contexto_visual": contexto_visual,
        "texto_respuesta": (
            texto_para_cliente.strip()
            if separador
            else "Recibí la imagen, pero necesito revisarla con más detalle."
        ),
        "formato_valido": separador,
    }


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
    Analiza con Claude una imagen enviada por un
    cliente: determina si es un comprobante de pago y, si lo es,
    extrae sus datos; si no lo es, genera directamente la respuesta
    natural que Bruno le da al cliente sobre lo que ve, considerando
    también el texto que haya escrito junto con la imagen.

    Normalmente usa una sola llamada. Solo repite el análisis cuando la
    respuesta no cumple el formato necesario para conservar sus datos.
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
CONTEXTO_VISUAL: [describe con precisión todo dato útil que se vea: productos,
texto, cantidades, pesos, medidas, unidades, subtotales y totales. Si hay una
tabla, conserva especialmente los totales y su unidad. No inventes datos.]
===RESPUESTA===
[tu respuesta natural sobre lo que ves en la imagen, tomando en cuenta el mensaje del cliente si mandó uno. Si es una captura de una tienda o de algo donde te está pidiendo ayuda, ayúdalo directamente con eso. Si no tiene nada que ver con Cúbico, dile con naturalidad qué ves y pregúntale en qué le puedes ayudar.]

No escribas nada antes de "ES_COMPROBANTE:" ni nada después del texto de la sección RESPUESTA. Esa sección debe quedar lista para mandarse tal cual al cliente por WhatsApp.
"""

    def consultar_vision(texto_instrucciones: str):
        return cliente_claude.messages.create(
            model="claude-sonnet-5",
            max_tokens=1200,
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
                            "media_type": detectar_mime_imagen(imagen_bytes),
                            "data": imagen_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": texto_instrucciones,
                    },
                ],
            }],
        )

    respuesta = consultar_vision(instrucciones)

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

    def extraer_texto(respuesta_vision) -> str:
        return "\n".join(
            bloque.text
            for bloque in respuesta_vision.content
            if bloque.type == "text"
        ).strip()

    texto_completo = extraer_texto(respuesta)
    analisis = interpretar_analisis_imagen(texto_completo)

    if not analisis["formato_valido"]:
        # Algunos modelos describen correctamente la foto pero omiten el
        # separador solicitado. Reintentamos una sola vez, poniendo especial
        # atención a manifiestos pequeños y a la fila final de totales.
        instrucciones_reintento = instrucciones + """

IMPORTANTE: tu respuesta anterior no respetó el formato. Vuelve a analizar la
imagen desde cero. Si contiene una tabla o manifiesto, lee los encabezados y la
última fila con especial cuidado; conserva exactamente los totales de peso y
CBM aunque el texto sea pequeño. Debes incluir literalmente ===RESPUESTA===.
"""
        respuesta = consultar_vision(instrucciones_reintento)
        texto_completo = extraer_texto(respuesta)
        analisis = interpretar_analisis_imagen(texto_completo)

    return analisis


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
