import socket
import secrets

import httpx
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/notificar", tags=["notificaciones"])

# Idioma con el que está aprobada la plantilla "carga_llegada" en
# Meta Business Manager. Si no coincide, Meta rechaza el envío con
# el error 132001 (mismo criterio que envio_masivo.py).
IDIOMA_PLANTILLA = "es"

VERSION_API_META = "v21.0"

# Hosts permitidos para llamar este endpoint interno: el propio
# servidor (127.0.0.1) y el backend de cubico.com.pa. Como "cubico.com.pa"
# no es una IP, se resuelve por DNS en cada arranque de proceso y se
# compara contra la IP real de quien llama.
HOSTS_PERMITIDOS = {"127.0.0.1"}
DOMINIO_PERMITIDO = "cubico.com.pa"


def _ip_del_cliente(request: Request) -> str:
    """
    IP real de quien llama. Si hay un proxy (nginx) delante, usamos el
    primer valor de X-Forwarded-For; si no, la IP directa de la conexión.
    """
    forwardeada = request.headers.get("x-forwarded-for")
    if forwardeada:
        return forwardeada.split(",")[0].strip()
    return request.client.host if request.client else ""


def _ip_autorizada(ip: str) -> bool:
    if ip in HOSTS_PERMITIDOS:
        return True
    try:
        ips_dominio = {
            info[4][0] for info in socket.getaddrinfo(DOMINIO_PERMITIDO, None)
        }
    except OSError:
        # Si el DNS falla no asumimos que está permitido: se rechaza.
        return False
    return ip in ips_dominio


class CargaLlegadaBody(BaseModel):
    telefono: str
    nombre: str
    codigo: str
    factura: str
    monto: str
    paquetes: str


def _construir_payload_carga_llegada(body: CargaLlegadaBody) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": body.telefono,
        "type": "template",
        "template": {
            "name": "carga_llegada",
            "language": {"code": IDIOMA_PLANTILLA},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": body.nombre},
                        {"type": "text", "text": body.codigo},
                        {"type": "text", "text": body.factura},
                        {"type": "text", "text": body.monto},
                    ],
                },
            ],
        },
    }


@router.post("/carga-llegada")
async def notificar_carga_llegada(
    request: Request,
    x_cubico_key: str = Header(default=""),
):
    if not _ip_autorizada(_ip_del_cliente(request)):
        return JSONResponse(status_code=403, content={"error": "Origen no autorizado"})

    if not secrets.compare_digest(x_cubico_key, settings.CUBICO_NOTIFY_KEY):
        return JSONResponse(status_code=401, content={"error": "Clave inválida"})

    try:
        cuerpo_json = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Cuerpo JSON inválido"})

    try:
        body = CargaLlegadaBody(**cuerpo_json)
    except Exception as error:
        return JSONResponse(status_code=400, content={"error": str(error)})

    payload = _construir_payload_carga_llegada(body)
    url_meta = (
        f"https://graph.facebook.com/{VERSION_API_META}/"
        f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as cliente_http:
            respuesta = await cliente_http.post(url_meta, headers=headers, json=payload)
    except httpx.RequestError as error:
        return JSONResponse(
            status_code=502,
            content={"error": f"No se pudo contactar a Meta: {error}"},
        )

    if respuesta.status_code == 200:
        return {"ok": True}

    try:
        detalle_error = respuesta.json().get("error", {})
        motivo = detalle_error.get("message", respuesta.text)
    except ValueError:
        motivo = respuesta.text

    return {"ok": False, "motivo": motivo}
