import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.api.whatsapp import NUMEROS_NOTIFICACION, enviar_mensaje_whatsapp, notificar_equipo_domicilio
from app.db.session_store import listar_sesiones_con_factura_pendiente, actualizar_sesion
from app.tools.facturas import consultar_facturas_por_codigo
from app.tools.paquetes import consultar_paquetes_por_codigo

log = logging.getLogger("scheduler")

# Mensaje fijo, sin pasar por Claude: esto corre todos los días sin
# intervención humana y no tiene sentido gastar tokens en algo tan simple.
MENSAJE_PING_DIARIO = "✅ Bot de Cúbico funcionando correctamente."

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


async def enviar_ping_diario():
    """
    Le manda un mensaje fijo a los números del equipo (NUMEROS_NOTIFICACION)
    una vez al día. WhatsApp solo permite mensajes de texto libre dentro de
    una ventana de 24h desde el último mensaje que la persona le mandó al
    bot; si nadie del equipo le escribe en un día, esa ventana se cierra y
    los avisos de escalamiento/comprobantes/retiro dejan de llegar. Este
    ping la mantiene abierta.
    """
    for numero in NUMEROS_NOTIFICACION:
        try:
            await enviar_mensaje_whatsapp(numero, MENSAJE_PING_DIARIO)
        except Exception as error:
            log.error(f"Error enviando ping diario a {numero}: {type(error).__name__}: {error}")


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
        id="ping_diario_equipo",
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
    scheduler.start()
    log.info(
        f"Scheduler iniciado: ping diario 8:00 AM + revisión de pagos "
        f"cada 30 min ({ZONA_HORARIA})."
    )
