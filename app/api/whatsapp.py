from fastapi import APIRouter, Request, HTTPException

from app.core.config import settings

router = APIRouter()


@router.get("/webhook")
def verificar_webhook(request: Request):
    """
    Endpoint de VERIFICACIÓN que Meta llama una sola vez, cuando
    configuras el webhook en Meta for Developers.

    Meta envía tres parámetros por la URL (query params):
      - hub.mode: siempre será "subscribe"
      - hub.verify_token: el token secreto que tú definiste
      - hub.challenge: un número aleatorio que debes devolver tal cual

    Si el token coincide con el nuestro, respondemos con el challenge
    y Meta confirma que esta URL es legítimamente nuestra.
    """
    modo = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if modo == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        # Meta espera el challenge como texto plano, no como JSON
        return int(challenge)

    # Si el token no coincide, rechazamos con un error 403 (Forbidden)
    raise HTTPException(status_code=403, detail="Token de verificación inválido")


def extraer_mensaje_entrante(payload: dict):
    """
    Recibe el JSON completo que manda Meta y extrae, de forma segura,
    el número de teléfono del cliente y el texto de su mensaje.

    Meta manda distintos tipos de eventos por el mismo webhook
    (mensajes nuevos, confirmaciones de lectura, actualizaciones de
    plantillas, etc.). Esta función solo nos interesa cuando el
    evento es un mensaje de texto real de un cliente — para todo lo
    demás, devuelve None, y el resto del código simplemente lo ignora.

    Devuelve un diccionario {"telefono": ..., "texto": ...} o None
    si el payload no contiene un mensaje de texto entrante.
    """
    try:
        entry = payload["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        # Si no hay "messages" en este evento, no es un mensaje nuevo
        # (puede ser un "status" de entrega/lectura, por ejemplo).
        if "messages" not in value:
            return None

        mensaje = value["messages"][0]

        # Por ahora solo manejamos mensajes de texto. Más adelante
        # podemos agregar soporte para imágenes, audios, etc.
        if mensaje.get("type") != "text":
            return None

        return {
            "telefono": mensaje["from"],
            "texto": mensaje["text"]["body"],
        }

    except (KeyError, IndexError, TypeError):
        # Si la estructura no es la esperada, no truena el servidor,
        # simplemente indicamos que no había un mensaje que procesar.
        return None


@router.post("/webhook")
async def recibir_mensaje(request: Request):
    """
    Endpoint que Meta llama CADA VEZ que llega un mensaje real de
    WhatsApp. Extrae el número de teléfono y el texto del cliente,
    y por ahora los imprime en consola — la respuesta automática
    la conectamos en el siguiente paso, con Claude API.
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

    # Meta espera un 200 OK rápido, sin importar el contenido de la
    # respuesta. Si no respondemos rápido, Meta reintenta el envío.
    return {"status": "recibido"}