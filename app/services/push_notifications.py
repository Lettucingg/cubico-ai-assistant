import asyncio
import json
from pathlib import Path

from app.core.config import settings
from app.db.session_store import eliminar_suscripcion_push, listar_suscripciones_push

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # El bot debe seguir vivo si aún no se instaló el extra.
    WebPushException = Exception
    webpush = None


def push_configurado() -> bool:
    ruta = Path(settings.PUSH_VAPID_PRIVATE_KEY_PATH)
    return bool(webpush and settings.PUSH_VAPID_PUBLIC_KEY.strip() and ruta.is_file())


def _enviar_a_dispositivos(payload: dict, usuarios: set[str] | None = None) -> dict:
    if not push_configurado():
        return {"enviadas": 0, "eliminadas": 0, "configurado": False}

    enviadas = 0
    eliminadas = 0
    for suscripcion in listar_suscripciones_push():
        if usuarios is not None and suscripcion["usuario"] not in usuarios:
            continue
        try:
            webpush(
                subscription_info={
                    "endpoint": suscripcion["endpoint"],
                    "keys": suscripcion["keys"],
                },
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=settings.PUSH_VAPID_PRIVATE_KEY_PATH,
                vapid_claims={"sub": settings.PUSH_VAPID_SUBJECT},
                timeout=8,
            )
            enviadas += 1
        except WebPushException as error:
            codigo = getattr(getattr(error, "response", None), "status_code", None)
            if codigo in (404, 410):
                eliminar_suscripcion_push(suscripcion["endpoint"])
                eliminadas += 1
            else:
                print(f"Error enviando Web Push: {type(error).__name__}: {error}")
        except Exception as error:
            print(f"Error inesperado enviando Web Push: {type(error).__name__}: {error}")

    return {"enviadas": enviadas, "eliminadas": eliminadas, "configurado": True}


async def notificar_informe_push(informe: dict, usuarios: set[str]) -> dict:
    datos = informe.get("datos")
    body = "Tu informe está listo. Revisa la actividad, los pendientes y la conexión de Bruno."
    if datos:
        pendientes = " · ".join(f"{datos[campo]} {nombre}" for campo, nombre in (
            ("humanos_pendientes", "atención humana"), ("pagos_pendientes", "pagos"),
            ("retiros_pendientes", "retiros"), ("domicilios_pendientes", "domicilios")))
        meta = "Meta conectada" if informe.get("estado_meta") == "conexión con Meta disponible" else "Revisar conexión de Bruno"
        actividad = f"{datos['conversaciones_hoy']} chats hoy · {datos['oportunidades_nuevas']} oportunidades. " if informe["tipo"] != "mañana" else ""
        body = f"{meta}. {actividad}Pendientes: {pendientes}. Toca para revisar."
    payload = {
        "title": "CÚBICO · " + ("Bruno y pendientes de hoy" if informe["tipo"] == "mañana" else "Así va tu negocio hoy"),
        "body": body,
        "url": f"/admin?informe={informe['id']}",
        "tag": f"cubico-informe-{informe['id']}",
        "informe_id": informe["id"],
    }
    return await asyncio.to_thread(_enviar_a_dispositivos, payload, usuarios)


async def notificar_panel_push(telefono: str, nombre: str | None, texto: str) -> dict:
    """Avisa sin bloquear el webhook ni la respuesta automática del bot."""
    payload = {
        "title": f"Nuevo mensaje · {nombre or telefono}",
        "body": texto[:160] or "Nuevo mensaje de WhatsApp",
        "telefono": telefono,
        "url": f"/admin?telefono={telefono}",
        "tag": f"cubico-{telefono}",
    }
    return await asyncio.to_thread(_enviar_a_dispositivos, payload)
