import httpx

from fastapi import APIRouter, Request, HTTPException

from app.core.config import settings
from app.ai.orchestrator import generar_respuesta
from app.db.session_store import obtener_o_crear_sesion, actualizar_sesion
from app.tools.clientes import verificar_cliente

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
        return int(challenge)

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

    async with httpx.AsyncClient() as client:
        respuesta = await client.post(url, headers=headers, json=payload)

    if respuesta.status_code != 200:
        print(f"Error al enviar mensaje a {telefono_destino}: {respuesta.text}")
    else:
        print(f"Mensaje enviado a {telefono_destino}: {texto}")

    return respuesta


def extraer_mensaje_entrante(payload: dict):
    """
    Recibe el JSON completo que manda Meta y extrae, de forma segura,
    el número de teléfono del cliente y el texto de su mensaje.
    """
    try:
        entry = payload["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            return None

        mensaje = value["messages"][0]

        if mensaje.get("type") != "text":
            return None

        return {
            "telefono": mensaje["from"],
            "texto": mensaje["text"]["body"],
        }

    except (KeyError, IndexError, TypeError):
        return None


def manejar_verificacion(sesion, texto_cliente: str) -> str:
    """
    Maneja el flujo de verificación de identidad, paso a paso.
    """
    if sesion.estado == "esperando_codigo":
        actualizar_sesion(
            sesion.telefono,
            estado="esperando_correo",
            codigo_cliente_temporal=texto_cliente.strip(),
        )
        return (
            "¡Hola! Para ayudarte, primero necesito verificar tu "
            "identidad. Por favor, escribe el correo electrónico "
            "con el que estás registrado en Cúbico."
        )

    if sesion.estado == "esperando_correo":
        codigo = sesion.codigo_cliente_temporal
        correo = texto_cliente.strip()

        if verificar_cliente(codigo, correo):
            actualizar_sesion(
                sesion.telefono,
                estado="verificado",
                codigo_cliente_verificado=codigo,
            )
            return (
                "¡Perfecto, tu identidad quedó verificada! ✅ "
                "Ahora puedo ayudarte con tus paquetes, facturas y "
                "cualquier otra consulta. ¿En qué te ayudo?"
            )
        else:
            actualizar_sesion(
                sesion.telefono,
                estado="esperando_codigo",
                codigo_cliente_temporal=None,
            )
            return (
                "No pude verificar esos datos. Por favor, escribe "
                "de nuevo tu código de cliente CBC (ej: CBC-0001)."
            )

    return "Escribe tu código de cliente CBC para comenzar."


@router.post("/webhook")
async def recibir_mensaje(request: Request):
    """
    Endpoint que Meta llama CADA VEZ que llega un mensaje real de
    WhatsApp. Verifica la identidad del cliente antes de dejarlo
    conversar libremente con Claude.
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

    print(f"Mensaje de {mensaje['telefono']}: {mensaje['texto']}")

    sesion = obtener_o_crear_sesion(mensaje["telefono"])

    if sesion.estado != "verificado":
        texto_respuesta = manejar_verificacion(sesion, mensaje["texto"])
    else:
        texto_respuesta = generar_respuesta(
            mensaje["texto"],
            codigo_cliente=sesion.codigo_cliente_verificado,
            )
    await enviar_mensaje_whatsapp(mensaje["telefono"], texto_respuesta)

    return {"status": "recibido"}