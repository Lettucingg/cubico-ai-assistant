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


@router.post("/webhook")
async def recibir_mensaje(request: Request):
    """
    Endpoint que Meta llama CADA VEZ que llega un mensaje real de
    WhatsApp. Por ahora solo lo imprimimos en consola para ver la
    estructura real de los datos que manda Meta — todavía no
    procesamos nada ni respondemos al cliente.
    """
    payload = await request.json()
    print("Mensaje recibido de WhatsApp:")
    print(payload)

    # Meta espera un 200 OK rápido, sin importar el contenido de la
    # respuesta. Si no respondemos rápido, Meta reintenta el envío.
    return {"status": "recibido"}
