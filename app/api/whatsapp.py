import asyncio

import httpx

from fastapi import APIRouter, BackgroundTasks, Request, HTTPException

from app.core.config import settings
from app.ai.orchestrator import generar_respuesta, redactar_respuesta_de_asesor
from app.db.session_store import (
    obtener_o_crear_sesion,
    obtener_sesion_existente,
    agregar_al_historial,
    actualizar_sesion,
    listar_sesiones_escaladas,
)
from app.tools.transcripcion import procesar_nota_de_voz
from app.tools.comprobantes import (
    descargar_imagen_de_whatsapp,
    analizar_comprobante,
    extraer_campos_comprobante,
)
from app.tools.clientes import obtener_nombre_completo_cliente

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


async def enviar_imagen_whatsapp(telefono_destino: str, media_id: str, caption: str = None):
    """
    Reenvía una imagen ya existente en WhatsApp (por su media_id)
    a otro número de teléfono.
    """
    url = f"https://graph.facebook.com/v21.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": telefono_destino,
        "type": "image",
        "image": {"id": media_id},
    }
    if caption:
        payload["image"]["caption"] = caption

    async with httpx.AsyncClient(timeout=10.0) as client:
        respuesta = await client.post(url, headers=headers, json=payload)

    if respuesta.status_code != 200:
        print(f"Error al enviar imagen a {telefono_destino}: {respuesta.text}")
    else:
        print(f"Imagen enviada a {telefono_destino}")

    return respuesta


# Números que pueden usar comandos de equipo (/responder, /resuelto,
# /pendientes). Sus mensajes normales NO se procesan como cliente.
NUMEROS_EQUIPO = ["50769837308"]

# Números que reciben notificaciones (escalamiento, comprobantes de
# pago) pero que SÍ pueden seguir siendo tratados como cliente normal
# en sus mensajes regulares.
NUMEROS_NOTIFICACION = ["50760348962", "50769837308"]


SEGUNDOS_ESPERA_BUFFER = 4.0

buffer_mensajes: dict[str, dict] = {}
tareas_pendientes: dict[str, asyncio.Task] = {}


PALABRAS_CLAVE_ESCALAMIENTO = [
    "dañado", "dañada", "dañó", "roto", "rota", "se rompió",
    "perdido", "perdida", "extraviado", "extraviada", "se perdió",
    "robado", "robaron", "no llegó", "no llego", "no ha llegado",
    "nunca llegó", "no me llegó", "no aparece", "desaparecido",
    "reclamo", "queja", "denuncia", "estafa", "fraude",
    "cobro incorrecto", "me cobraron mal", "cobro mal", "cobro de más",
    "cobro doble", "defectuoso", "defectuosa", "incompleto", "incompleta",
    "le falta", "faltante", "vino mal", "llegó roto", "llegó dañado",
    "quiero un reembolso", "quiero mi dinero de vuelta", "devolución", "devolucion",
    "quiero hablar con una persona", "quiero hablar con alguien",
    "hablar con un humano", "necesito hablar con un asesor",
]


def detectar_posible_queja(texto: str) -> bool:
    """
    Revisa si el mensaje del cliente contiene palabras o frases que
    sugieren un problema real (paquete dañado/perdido, cobro
    incorrecto, reclamo formal, etc.). Se usa para forzar el
    escalamiento a humano directamente en código, sin depender de
    que Claude decida invocar la herramienta escalar_a_humano
    correctamente.
    """
    texto_normalizado = texto.lower()
    return any(palabra in texto_normalizado for palabra in PALABRAS_CLAVE_ESCALAMIENTO)


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
    for numero in NUMEROS_NOTIFICACION:
        try:
            await enviar_mensaje_whatsapp(numero, mensaje)
        except Exception as error:
            import traceback
            print(f"Error notificando a {numero}: {type(error).__name__}: {error}")
            traceback.print_exc()


async def notificar_equipo_comprobante(telefono_cliente: str, detalle_comprobante: str, media_id: str):
    """
    Notifica a los números del equipo cuando un cliente envía un
    comprobante de pago: identifica al cliente (si está verificado),
    manda el detalle en texto y reenvía la imagen real, para que lo
    verifiquen y lo registren.
    """
    sesion = obtener_o_crear_sesion(telefono_cliente)

    linea_cliente = f"⚠️ Cliente no identificado — verificar por wa.me/{telefono_cliente}"
    if sesion.codigo_cliente_verificado:
        resultado_cliente = obtener_nombre_completo_cliente(sesion.codigo_cliente_verificado)
        if resultado_cliente["encontrado"]:
            linea_cliente = (
                f"Cliente: {resultado_cliente['nombre_completo']} "
                f"({sesion.codigo_cliente_verificado})"
            )

    campos = extraer_campos_comprobante(detalle_comprobante)

    mensaje = (
        f"📸 *Comprobante de pago recibido*\n\n"
        f"{linea_cliente}\n\n"
        f"Monto: {campos['monto']}\n"
        f"Fecha: {campos['fecha']}\n"
        f"Referencia: {campos['referencia']}\n"
        f"Método: {campos['metodo']}\n\n"
        f"wa.me/{telefono_cliente}"
    )
    for numero in NUMEROS_NOTIFICACION:
        try:
            await enviar_mensaje_whatsapp(numero, mensaje)
            await enviar_imagen_whatsapp(numero, media_id, caption="📸 Comprobante recibido")
        except Exception as error:
            import traceback
            print(f"Error notificando comprobante a {numero}: {type(error).__name__}: {error}")
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
    - Si hay más de 2 partes, la primera se manda tal cual y el resto
      se une en un solo segundo mensaje, para no mandar más de 2
      mensajes de WhatsApp por respuesta.
    - Antes de cada parte, muestra el indicador de "escribiendo..."
      durante un tiempo proporcional al largo de esa parte.
    - Manda cada parte como un mensaje de WhatsApp separado.

    Esto hace que respuestas largas se sientan como una persona
    escribiendo uno o dos mensajes seguidos, en vez de un bloque de
    texto instantáneo o una ráfaga de mensajes sueltos.
    """
    partes = [p.strip() for p in texto_completo.split("\n\n") if p.strip()]

    if not partes:
        partes = [texto_completo]

    if len(partes) > 2:
        partes = [partes[0], "\n\n".join(partes[1:])]

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

        if mensaje.get("type") == "image":
            return {
                "telefono": mensaje["from"],
                "texto": None,
                "media_id": mensaje["image"]["id"],
                "message_id": mensaje["id"],
                "tipo": "image",
            }

        return None

    except (KeyError, IndexError, TypeError):
        return None


async def _procesar_buffer_tras_espera(telefono: str):
    """
    Espera SEGUNDOS_ESPERA_BUFFER antes de procesar el buffer
    acumulado de un número. Si llega un mensaje nuevo de ese mismo
    número mientras espera, esta tarea se cancela desde
    agregar_mensaje_a_buffer y una tarea nueva reinicia la espera.
    """
    try:
        await asyncio.sleep(SEGUNDOS_ESPERA_BUFFER)
    except asyncio.CancelledError:
        return

    mensaje_combinado = buffer_mensajes.pop(telefono, None)
    tareas_pendientes.pop(telefono, None)

    if mensaje_combinado is None:
        return

    await procesar_mensaje_en_segundo_plano(mensaje_combinado)


async def agregar_mensaje_a_buffer(mensaje: dict):
    """
    Punto de entrada para cada mensaje entrante (texto o audio ya
    transcrito). Lo acumula en el buffer del número y reinicia el
    temporizador de espera, para agrupar ráfagas de mensajes seguidos
    del mismo cliente en una sola respuesta.
    """
    if mensaje["tipo"] == "audio":
        try:
            texto_transcrito = await procesar_nota_de_voz(mensaje["media_id"])
            print(f"Transcripción de audio: {texto_transcrito}")
            mensaje = {**mensaje, "texto": texto_transcrito, "tipo": "text"}
        except Exception as error:
            print(f"Error transcribiendo nota de voz de {mensaje['telefono']}: {error}")
            await enviar_mensaje_whatsapp(
                mensaje["telefono"],
                "No pude escuchar bien tu nota de voz, ¿puedes escribirlo o intentar de nuevo?",
            )
            return

    telefono = mensaje["telefono"]

    mensaje_en_buffer = buffer_mensajes.get(telefono)
    if mensaje_en_buffer and mensaje_en_buffer["tipo"] == "text" and mensaje["tipo"] == "text":
        # Ambos son texto: se concatenan para agrupar la ráfaga en un
        # solo mensaje combinado.
        mensaje_en_buffer["texto"] += f"\n{mensaje['texto']}"
        mensaje_en_buffer["message_id"] = mensaje["message_id"]
    else:
        # Tipos mezclados (texto/imagen/audio) o buffer vacío: no hay
        # forma segura de concatenar (texto podría ser None), así que
        # el mensaje nuevo reemplaza al buffer y se procesa por su
        # cuenta, priorizando el último tipo recibido.
        buffer_mensajes[telefono] = dict(mensaje)

    tarea_anterior = tareas_pendientes.get(telefono)
    if tarea_anterior and not tarea_anterior.done():
        tarea_anterior.cancel()

    tareas_pendientes[telefono] = asyncio.create_task(_procesar_buffer_tras_espera(telefono))


async def procesar_mensaje_en_segundo_plano(mensaje: dict):
    """
    Hace todo el trabajo pesado de un mensaje ya combinado del buffer
    (verificación, llamada a Claude, historial y envío de la
    respuesta) fuera del ciclo de request/response del webhook, para
    que Meta reciba un 200 inmediato y no reintente por timeout.
    """
    print(f"Mensaje de {mensaje['telefono']}: {mensaje['texto']}")

    try:
        if mensaje["tipo"] == "image":
            imagen_bytes = await descargar_imagen_de_whatsapp(mensaje["media_id"])
            resultado = analizar_comprobante(imagen_bytes)

            if resultado["es_comprobante"]:
                await notificar_equipo_comprobante(
                    mensaje["telefono"], resultado["detalle_completo"], mensaje["media_id"]
                )
                await enviar_mensaje_whatsapp(
                    mensaje["telefono"],
                    "Recibí tu comprobante, nuestro equipo lo va a verificar y registrar en breve.",
                )
            else:
                await enviar_mensaje_whatsapp(
                    mensaje["telefono"],
                    "Recibí tu imagen, pero no parece ser un comprobante de pago. ¿En qué te puedo ayudar?",
                )
            return

        sesion = obtener_o_crear_sesion(mensaje["telefono"])
        estaba_escalado_antes = sesion.necesita_atencion_humana

        if detectar_posible_queja(mensaje["texto"]):
            actualizar_sesion(
                mensaje["telefono"],
                necesita_atencion_humana=True,
                motivo_escalamiento="Posible queja detectada automaticamente",
            )

        texto_respuesta = generar_respuesta(
            mensaje["texto"],
            telefono=mensaje["telefono"],
            codigo_cliente=sesion.codigo_cliente_verificado,
            historial=sesion.obtener_historial(),
        )

        agregar_al_historial(sesion.telefono, "user", mensaje["texto"])
        agregar_al_historial(sesion.telefono, "assistant", texto_respuesta)

        sesion_actualizada = obtener_o_crear_sesion(mensaje["telefono"])
        print(f"[DEBUG] necesita_atencion_humana = {sesion_actualizada.necesita_atencion_humana}")
        if sesion_actualizada.necesita_atencion_humana and not estaba_escalado_antes:
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
        sesion_cliente = obtener_sesion_existente(numero_cliente)

        if sesion_cliente is None or not sesion_cliente.necesita_atencion_humana:
            await enviar_mensaje_whatsapp(
                telefono_asesor,
                f"⚠️ {numero_cliente} no tiene un caso escalado activo. No se envió nada.",
            )
            return

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

    if mensaje["telefono"] in NUMEROS_EQUIPO:
        if mensaje["tipo"] == "text":
            partes_comando = mensaje["texto"].strip().split()
            if len(partes_comando) == 2 and partes_comando[0] == "/resuelto":
                numero_cliente = partes_comando[1]
                encontrada = actualizar_sesion(
                    numero_cliente, necesita_atencion_humana=False, motivo_escalamiento=None
                )
                if encontrada:
                    await enviar_mensaje_whatsapp(
                        mensaje["telefono"],
                        f"✅ Marcado como resuelto para {numero_cliente}.",
                    )
                else:
                    await enviar_mensaje_whatsapp(
                        mensaje["telefono"],
                        f"⚠️ No encontré una conversación con el número {numero_cliente}.",
                    )
                return {"status": "comando_procesado"}

            if len(partes_comando) == 1 and partes_comando[0] == "/pendientes":
                pendientes = listar_sesiones_escaladas()
                if not pendientes:
                    await enviar_mensaje_whatsapp(
                        mensaje["telefono"],
                        "✅ No hay casos pendientes en este momento.",
                    )
                else:
                    lineas = [
                        f"{i}. wa.me/{s.telefono} - {s.motivo_escalamiento or 'No especificado'}"
                        for i, s in enumerate(pendientes, start=1)
                    ]
                    texto = f"📋 Casos pendientes ({len(pendientes)}):\n\n" + "\n".join(lineas)
                    await enviar_mensaje_whatsapp(mensaje["telefono"], texto)
                return {"status": "comando_procesado"}

            partes_responder = mensaje["texto"].strip().split(maxsplit=2)
            if len(partes_responder) == 3 and partes_responder[0] == "/responder":
                numero_cliente = partes_responder[1]
                solucion_del_asesor = partes_responder[2]
                background_tasks.add_task(
                    procesar_respuesta_de_asesor, mensaje["telefono"], numero_cliente, solucion_del_asesor
                )
                return {"status": "comando_procesado"}

        # Un número del equipo escribiendo algo que no es un comando
        # reconocido no debe tratarse como cliente: no debe crear ni
        # actualizar una Sesion, ni pasar por generar_respuesta/escalamiento.
        await enviar_mensaje_whatsapp(
            mensaje["telefono"],
            "No reconozco ese comando. Usa /responder <numero> <mensaje>, /resuelto <numero> o /pendientes.",
        )
        return {"status": "comando_no_reconocido"}

    background_tasks.add_task(agregar_mensaje_a_buffer, mensaje)

    return {"status": "recibido"}