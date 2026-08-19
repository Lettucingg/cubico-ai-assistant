import asyncio

import httpx

from fastapi import APIRouter, BackgroundTasks, Request, HTTPException

from app.core.config import settings
from app.ai.orchestrator import generar_respuesta
from app.db.session_store import obtener_o_crear_sesion, agregar_al_historial
from app.tools.transcripcion import procesar_nota_de_voz

router = APIRouter()


@router.get("/webhook")
def verificar_webhook(request: Request):
    """
    Endpoint de VERIFICACIÓN que Meta llama una sola vez, cuando
    configuras el webhook en Meta for Developers.
    """
    modo = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if modo == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        try:
            return int(challenge)
        except (TypeError, ValueError):
            raise HTTPException(status_code=403, detail="Challenge inválido")

    raise HTTPException(status_code=403, detail="Token de verificación inválido")


async def enviar_mensaje_whatsapp(telefono_destino: str, texto: str):
    """
    Envía un mensaje de texto a un número de WhatsApp usando la API
    de Meta (WhatsApp Cloud API).
    """
    url = f"https://graph.facebook.com/v21.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": telefono_destino,
        "type": "text",
        "text": {"body": texto},
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        respuesta = await client.post(url, headers=headers, json=payload)

    if respuesta.status_code != 200:
        print(f"Error al enviar mensaje a {telefono_destino}: {respuesta.text}")
    else:
        print(f"Mensaje enviado a {telefono_destino}: {texto}")

    return respuesta


async def marcar_leido_y_escribiendo(message_id: str):
    """
    Marca el mensaje del cliente como leído y muestra el indicador
    de "escribiendo..." en su chat, mientras preparamos la respuesta
    real. Se apaga solo cuando mandamos la respuesta, o después de
    25 segundos si no respondemos.
    """
    url = f"https://graph.facebook.com/v21.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {"type": "text"},
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, headers=headers, json=payload)
    except httpx.RequestError:
        pass


async def enviar_respuesta_natural(telefono_destino: str, texto_completo: str, message_id: str):
    """
    Envía la respuesta del bot simulando una escritura más humana:
    - Divide el texto en partes (por doble salto de línea, si existen;
      si no, lo manda completo como un solo mensaje).
    - Antes de cada parte, muestra el indicador de "escribiendo..."
      durante un tiempo proporcional al largo de esa parte.
    - Manda cada parte como un mensaje de WhatsApp separado.

    Esto hace que respuestas largas se sientan como una persona
    escribiendo varios mensajes seguidos, en vez de un bloque de
    texto instantáneo.
    """
    partes = [p.strip() for p in texto_completo.split("\n\n") if p.strip()]

    if not partes:
        partes = [texto_completo]

    for i, parte in enumerate(partes):
        # Simula tiempo de escritura: ~0.05 segundos por palabra,
        # con un mínimo de 1 segundo y un máximo de 4 segundos,
        # para no hacer esperar demasiado en respuestas largas.
        palabras = len(parte.split())
        tiempo_espera = min(max(palabras * 0.05, 1.0), 4.0)

        await marcar_leido_y_escribiendo(message_id)
        await asyncio.sleep(tiempo_espera)
        await enviar_mensaje_whatsapp(telefono_destino, parte)

        # Pequeña pausa entre mensajes consecutivos, como si la
        # persona hiciera una breve pausa antes de seguir escribiendo.
        if i < len(partes) - 1:
            await asyncio.sleep(0.8)


def extraer_mensaje_entrante(payload: dict):
    """
    Recibe el JSON completo que manda Meta y extrae, de forma segura,
    el número de teléfono del cliente y el contenido de su mensaje
    (texto o nota de voz).
    """
    try:
        entry = payload["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            return None

        mensaje = value["messages"][0]

        if mensaje.get("type") == "text":
            return {
                "telefono": mensaje["from"],
                "texto": mensaje["text"]["body"],
                "media_id": None,
                "message_id": mensaje["id"],
                "tipo": "text",
            }

        if mensaje.get("type") == "audio":
            return {
                "telefono": mensaje["from"],
                "texto": None,
                "media_id": mensaje["audio"]["id"],
                "message_id": mensaje["id"],
                "tipo": "audio",
            }

        return None

    except (KeyError, IndexError, TypeError):
        return None


async def procesar_mensaje_en_segundo_plano(mensaje: dict):
    """
    Hace todo el trabajo pesado de un mensaje entrante (transcripción
    de audio si aplica, verificación, llamada a Claude, historial y
    envío de la respuesta) fuera del ciclo de request/response del
    webhook, para que Meta reciba un 200 inmediato y no reintente por
    timeout.
    """
    if mensaje["tipo"] == "audio":
        try:
            texto_transcrito = await procesar_nota_de_voz(mensaje["media_id"])
            print(f"Transcripción de audio: {texto_transcrito}")
            mensaje["texto"] = texto_transcrito
        except Exception as error:
            print(f"Error transcribiendo nota de voz de {mensaje['telefono']}: {error}")
            texto_respaldo = (
                "No pude escuchar bien tu nota de voz, ¿puedes escribirlo "
                "o intentar de nuevo?"
            )
            await enviar_mensaje_whatsapp(mensaje["telefono"], texto_respaldo)
            return

    print(f"Mensaje de {mensaje['telefono']}: {mensaje['texto']}")

    try:
        sesion = obtener_o_crear_sesion(mensaje["telefono"])

        texto_respuesta = generar_respuesta(
            mensaje["texto"],
            telefono=mensaje["telefono"],
            codigo_cliente=sesion.codigo_cliente_verificado,
            historial=sesion.obtener_historial(),
        )

        agregar_al_historial(sesion.telefono, "user", mensaje["texto"])
        agregar_al_historial(sesion.telefono, "assistant", texto_respuesta)

        await enviar_respuesta_natural(mensaje["telefono"], texto_respuesta, mensaje["message_id"])

    except Exception as error:
        print(f"Error procesando mensaje de {mensaje['telefono']}: {error}")


@router.post("/webhook")
async def recibir_mensaje(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint que Meta llama CADA VEZ que llega un mensaje real de
    WhatsApp. Responde de inmediato y delega el procesamiento pesado
    (transcripción, Claude, envío) a una tarea en segundo plano.
    """
    try:
        payload = await request.json()
    except Exception:
        print("Se recibió una petición sin un JSON válido.")
        return {"status": "ignorado", "razon": "cuerpo vacío o inválido"}

    mensaje = extraer_mensaje_entrante(payload)

    if mensaje is None:
        print("Evento recibido, pero no es un mensaje de texto entrante (ignorado).")
        return {"status": "ignorado", "razon": "no es un mensaje de texto"}

    background_tasks.add_task(procesar_mensaje_en_segundo_plano, mensaje)

    return {"status": "recibido"}