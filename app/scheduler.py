import logging
import httpx

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.api.whatsapp import enviar_mensaje_whatsapp, notificar_equipo_domicilio
from app.core.config import settings
from app.services.daily_reports import datos_informe, informe_manana, informe_cierre
from app.db.session_store import (
    listar_sesiones_con_factura_pendiente,
    actualizar_sesion,
)
from app.tools.facturas import consultar_facturas_por_codigo
from app.tools.paquetes import consultar_paquetes_por_codigo

log = logging.getLogger("scheduler")

# También fijo, sin Claude: se dispara solo, cada 30 minutos, y no
# amerita gastar una llamada a la API por algo tan simple.
MENSAJE_PAGO_CONFIRMADO = "✅ Ya confirmamos tu pago de la factura {codigo}. Tu envío puede proceder con normalidad."
MENSAJE_DOMICILIO_PIDE_DIRECCION = (
    "✅ Ya confirmamos tu pago de la factura {codigo}. Para coordinar la "
    "entrega a domicilio, pásame la dirección exacta."
)
MENSAJE_DOMICILIO_NOTIFICADO = (
    "✅ Ya confirmamos tu pago de la factura {codigo}. Tu entrega a "
    "domicilio quedó notificada al equipo."
)

ZONA_HORARIA = "America/Panama"

scheduler = AsyncIOScheduler(timezone=ZONA_HORARIA)


async def _informe_equipo(tipo: str):
    grupo = settings.CUBICO_TEAM_REPORT_GROUP_ID.strip()
    plantilla = settings.CUBICO_TEAM_REPORT_TEMPLATE.strip()
    if not grupo or not plantilla:
        log.warning("Informe %s omitido: falta grupo o plantilla aprobada", tipo)
        return

    try:
        datos = datos_informe()
    except Exception:
        log.exception("No se pudo consultar la base de datos para el informe %s", tipo)
        datos = None
    url = f"https://graph.facebook.com/v21.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}
    async with httpx.AsyncClient(timeout=12) as cliente:
        try:
            comprobacion = await cliente.get(
                f"https://graph.facebook.com/v21.0/{settings.WHATSAPP_PHONE_NUMBER_ID}",
                headers=headers,
            )
            estado = "conexión con Meta disponible" if comprobacion.is_success else "sin confirmar conexión con Meta"
        except httpx.HTTPError:
            estado = "sin confirmar conexión con Meta"
        mensaje = (
            (informe_manana if tipo == "mañana" else informe_cierre)(datos, estado)
            if datos is not None else
            "Cúbico · Informe de jornada: no se pudo consultar la base de datos. "
            f"Meta: {estado}. Revisar https://bot.cubico.com.pa/admin"
        )
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "group",
            "to": grupo,
            "type": "template",
            "template": {
                "name": plantilla,
                "language": {"code": settings.CUBICO_TEAM_REPORT_TEMPLATE_LANGUAGE},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": mensaje}]}],
            },
        }
        respuesta = await cliente.post(url, headers=headers, json=payload)
        if not respuesta.is_success:
            log.error("Informe %s rechazado por Meta (HTTP %s): %s", tipo, respuesta.status_code, respuesta.text[:500])
            respuesta.raise_for_status()
        log.info("Informe %s aceptado por Meta para el grupo configurado", tipo)


async def enviar_ping_diario():
    """Informe de apertura para el grupo configurado a las 8:00 de Panamá."""
    await _informe_equipo("mañana")


async def resumen_fin_dia():
    """Informe de cierre para el grupo configurado a las 17:00 de Panamá."""
    await _informe_equipo("cierre")


async def _continuar_domicilio_tras_pago_confirmado(sesion, codigo_factura: str):
    """
    Retoma una solicitud de entrega a domicilio que había quedado
    bloqueada por saldo pendiente (tipo_seguimiento_pago="domicilio"),
    ahora que el pago de esa factura ya se confirmó.

    Si el cliente ya había dado la dirección en el intento anterior,
    notifica al equipo directamente, como si el cliente lo hubiera
    vuelto a pedir. Si no, le pide la dirección.
    """
    if not sesion.direccion_domicilio:
        await enviar_mensaje_whatsapp(
            sesion.telefono,
            MENSAJE_DOMICILIO_PIDE_DIRECCION.format(codigo=codigo_factura),
        )
        actualizar_sesion(
            sesion.telefono, factura_pendiente_notificacion=None, tipo_seguimiento_pago=None
        )
        return

    resultado_paquetes = consultar_paquetes_por_codigo(sesion.codigo_cliente_verificado)
    trackings = [
        p["tracking"]
        for p in resultado_paquetes.get("paquetes", [])
        if p.get("estado_cargo") == "notificado"
    ]

    actualizar_sesion(
        sesion.telefono,
        solicitud_domicilio_pendiente=True,
        paquetes_a_domicilio=", ".join(trackings),
        factura_pendiente_notificacion=None,
        tipo_seguimiento_pago=None,
    )

    await notificar_equipo_domicilio(
        sesion.telefono, sesion.codigo_cliente_verificado, sesion.direccion_domicilio
    )
    await enviar_mensaje_whatsapp(
        sesion.telefono,
        MENSAJE_DOMICILIO_NOTIFICADO.format(codigo=codigo_factura),
    )


async def revisar_pagos_pendientes():
    """
    Cada 30 min revisa las sesiones con una factura marcada como
    pendiente (marcar_pago_pendiente_seguimiento) y, si ya aparece
    pagada, retoma el flujo correspondiente: si el seguimiento era para
    una entrega a domicilio bloqueada por el pago, continúa ese flujo
    en vez del aviso genérico. En ambos casos limpia la marca para no
    repetir el aviso.
    """
    for sesion in listar_sesiones_con_factura_pendiente():
        codigo_cliente = sesion.codigo_cliente_verificado
        codigo_factura = sesion.factura_pendiente_notificacion

        if not codigo_cliente or not codigo_factura:
            continue

        resultado = consultar_facturas_por_codigo(codigo_cliente)
        if not resultado.get("encontrado"):
            continue

        factura = next(
            (f for f in resultado["facturas"] if f["codigo"] == codigo_factura),
            None,
        )
        if factura is None or factura["estado"] != "pagado":
            continue

        try:
            if sesion.tipo_seguimiento_pago == "domicilio":
                await _continuar_domicilio_tras_pago_confirmado(sesion, codigo_factura)
            else:
                await enviar_mensaje_whatsapp(
                    sesion.telefono,
                    MENSAJE_PAGO_CONFIRMADO.format(codigo=codigo_factura),
                )
                actualizar_sesion(sesion.telefono, factura_pendiente_notificacion=None)
        except Exception as error:
            log.error(
                f"Error avisando pago confirmado a {sesion.telefono}: "
                f"{type(error).__name__}: {error}"
            )


def iniciar_scheduler():
    """Registra los jobs periódicos y arranca el scheduler. Se llama una
    sola vez, al iniciar la aplicación FastAPI."""
    scheduler.add_job(
        enviar_ping_diario,
        CronTrigger(hour=8, minute=0, timezone=ZONA_HORARIA),
        id="informe_apertura_equipo",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        revisar_pagos_pendientes,
        IntervalTrigger(minutes=30),
        id="revisar_pagos_pendientes",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        resumen_fin_dia,
        CronTrigger(hour=17, minute=0, timezone=ZONA_HORARIA),
        id="resumen_fin_dia",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    log.info(
        f"Scheduler iniciado: informe 8:00 AM + revisión de pagos "
        f"cada 30 min + resumen fin de día 5:00 PM ({ZONA_HORARIA})."
    )
