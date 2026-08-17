import httpx

from fastapi import APIRouter, Request, HTTPException

from app.core.config import settings
from app.ai.orchestrator import generar_respuesta

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

        print(f"[DEBUG] Status code: {respuesta.status_code}")
    print(f"[DEBUG] Respuesta completa: {respuesta.text}")

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


@router.post("/webhook")
async def recibir_mensaje(request: Request):
    """
    Endpoint que Meta llama CADA VEZ que llega un mensaje real de
    WhatsApp. Extrae el mensaje, genera una respuesta con Claude,
    y la envía de vuelta al cliente.
    """
    try:
        payload = await request.json()
    except Exception:
        print("Se recibió una petición sin un JSON válido.")
        return {"status": "ignorado", "razon": "cuerpo vacío o inválido"}
    except (KeyError, IndexError, TypeError):
        pass

    mensaje = extraer_mensaje_entrante(payload)

    if mensaje is None:
        print("Evento recibido, pero no es un mensaje de texto entrante (ignorado).")
        return {"status": "ignorado", "razon": "no es un mensaje de texto"}

    print(f"Mensaje de {mensaje['telefono']}: {mensaje['texto']}")

    texto_respuesta = generar_respuesta(mensaje["texto"])
    await enviar_mensaje_whatsapp(mensaje["telefono"], texto_respuesta)

    return {"status": "recibido"}