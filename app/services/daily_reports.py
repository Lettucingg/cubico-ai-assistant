"""Informes breves para el equipo, a partir del estado persistido de Bruno."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func

from app.db.session_store import OportunidadComercial, Sesion, SessionSesiones, UsoIA


PANAMA = ZoneInfo("America/Panama")


def _inicio_hoy_utc() -> datetime:
    hoy = datetime.now(PANAMA).replace(hour=0, minute=0, second=0, microsecond=0)
    return hoy.astimezone(timezone.utc).replace(tzinfo=None)


def datos_informe() -> dict:
    """Cuenta actividad de hoy y pendientes actuales; no mezcla ambas métricas."""
    db = SessionSesiones()
    try:
        inicio = _inicio_hoy_utc()
        sesiones = db.query(Sesion).all()
        costo = db.query(func.coalesce(func.sum(UsoIA.costo_usd), 0)).filter(UsoIA.creado_en >= inicio).scalar()
        nuevas = db.query(OportunidadComercial).filter(OportunidadComercial.creada_en >= inicio).count()
        return {
            "conversaciones_hoy": sum(bool(s.actualizado_en and s.actualizado_en >= inicio) for s in sesiones),
            "humanos_pendientes": sum(bool(s.necesita_atencion_humana) for s in sesiones),
            "pagos_pendientes": sum(bool(s.pago_reportado and not s.pago_confirmado) for s in sesiones),
            "retiros_pendientes": sum(bool(s.aviso_retiro_pendiente and not s.entregado) for s in sesiones),
            "domicilios_pendientes": sum(bool(s.solicitud_domicilio_pendiente and not s.entregado) for s in sesiones),
            "oportunidades_nuevas": nuevas,
            "costo_hoy": float(costo or 0),
            "fecha": datetime.now(PANAMA).strftime("%d/%m/%Y"),
        }
    finally:
        db.close()


def informe_manana(datos: dict, estado_api: str) -> str:
    pendientes = (
        f"{datos['humanos_pendientes']} atención humana · "
        f"{datos['pagos_pendientes']} pagos · "
        f"{datos['retiros_pendientes']} retiros · "
        f"{datos['domicilios_pendientes']} domicilios"
    )
    return (
        f"Cúbico · Inicio de jornada ({datos['fecha']})\n"
        f"Bruno: {estado_api}. Base de datos: disponible.\n"
        f"Pendientes al iniciar: {pendientes}.\n"
        "Panel: https://bot.cubico.com.pa/admin"
    )


def informe_cierre(datos: dict, estado_api: str) -> str:
    return (
        f"Cúbico · Cierre ({datos['fecha']})\n"
        f"Bruno ahora: {estado_api}.\n"
        f"Hoy: {datos['conversaciones_hoy']} conversaciones con actividad · "
        f"{datos['oportunidades_nuevas']} oportunidades nuevas · "
        f"IA ${datos['costo_hoy']:.2f}.\n"
        f"Quedan pendientes: {datos['humanos_pendientes']} atención humana · "
        f"{datos['pagos_pendientes']} pagos · "
        f"{datos['retiros_pendientes']} retiros · "
        f"{datos['domicilios_pendientes']} domicilios.\n"
        "Panel: https://bot.cubico.com.pa/admin"
    )
