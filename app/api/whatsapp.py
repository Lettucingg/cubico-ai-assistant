import asyncio

import httpx

from fastapi import APIRouter, BackgroundTasks, Request, HTTPException

from app.core.config import settings
from app.ai.orchestrator import generar_respuesta, redactar_respuesta_de_asesor
from app.db.session_store import obtener_o_crear_sesion, agregar_al_historial, actualizar_sesion
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


NUMEROS_EQUIPO = ["50760348962", "50769837308"]


async def notificar_equipo_escalamiento(telefono_cliente: str, texto_cliente: str, motivo: str):
    """
    Notifica a los números del equipo cuando una conversación necesita
    atención humana.
    """
    mensaje = (
        f"🚨 *Escalamiento a humano*\n\n"
        f"Cliente: wa.me/{telefono_cliente}\n"
        f"Motivo: {motivo}\n"
        f"Último mensaje: \"{texto_cliente}\""
    )
    for numero in NUMEROS_EQUIPO:
        try:
            await enviar_mensaje_whatsapp(numero, mensaje)
        except Exception as error:
            import traceback
            print(f"Error notificando a {numero}: {type(error).__name__}: {error}")
            traceback.print_exc()


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

        sesion_actualizada = obtener_o_crear_sesion(mensaje["telefono"])
        if sesion_actualizada.necesita_atencion_humana:
            await notificar_equipo_escalamiento(
                mensaje["telefono"],
                mensaje["texto"],
                sesion_actualizada.motivo_escalamiento or "No especificado",
            )

        await enviar_respuesta_natural(mensaje["telefono"], texto_respuesta, mensaje["message_id"])

    except Exception as error:
        print(f"Error procesando mensaje de {mensaje['telefono']}: {error}")
        try:
            await enviar_mensaje_whatsapp(
                mensaje["telefono"],
                "Tuve un problema procesando tu mensaje, ¿puedes intentarlo de nuevo?",
            )
        except Exception as error_envio:
            print(f"Error enviando mensaje de respaldo a {mensaje['telefono']}: {error_envio}")


async def procesar_respuesta_de_asesor(telefono_asesor: str, numero_cliente: str, solucion_del_asesor: str):
    """
    Toma la solución que un miembro del equipo escribió con el
    comando /responder, la redacta con el tono normal de Bruno
    (como si él mismo hubiera resuelto el caso) y se la envía al
    cliente, cerrando el escalamiento.
    """
    try:
        sesion_cliente = obtener_o_crear_sesion(numero_cliente)
        historial = sesion_cliente.obtener_historial()

        texto_cliente_original = next(
            (m["content"] for m in reversed(historial) if m["role"] == "user"),
            "el cliente escaló su caso a un asesor",
        )

        texto_redactado = redactar_respuesta_de_asesor(texto_cliente_original, solucion_del_asesor)

        agregar_al_historial(numero_cliente, "assistant", texto_redactado)
        await enviar_respuesta_natural(numero_cliente, texto_redactado, message_id="")

        actualizar_sesion(numero_cliente, necesita_atencion_humana=False, motivo_escalamiento=None)

        await enviar_mensaje_whatsapp(telefono_asesor, f"✅ Respuesta enviada a {numero_cliente}.")

    except Exception as error:
        print(f"Error procesando /responder para {numero_cliente}: {error}")
        await enviar_mensaje_whatsapp(
            telefono_asesor,
            f"⚠️ No pude enviar la respuesta a {numero_cliente}, intenta de nuevo.",
        )


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

    if mensaje["tipo"] == "text" and mensaje["telefono"] in NUMEROS_EQUIPO:
        partes_comando = mensaje["texto"].strip().split()
        if len(partes_comando) == 2 and partes_comando[0] == "/resuelto":
            numero_cliente = partes_comando[1]
            actualizar_sesion(numero_cliente, necesita_atencion_humana=False, motivo_escalamiento=None)
            await enviar_mensaje_whatsapp(
                mensaje["telefono"],
                f"✅ Marcado como resuelto para {numero_cliente}.",
            )
            return {"status": "comando_procesado"}

        partes_responder = mensaje["texto"].strip().split(maxsplit=2)
        if len(partes_responder) == 3 and partes_responder[0] == "/responder":
            numero_cliente = partes_responder[1]
            solucion_del_asesor = partes_responder[2]
            background_tasks.add_task(
                procesar_respuesta_de_asesor, mensaje["telefono"], numero_cliente, solucion_del_asesor
            )
            return {"status": "comando_procesado"}

    background_tasks.add_task(procesar_mensaje_en_segundo_plano, mensaje)

    return {"status": "recibido"}