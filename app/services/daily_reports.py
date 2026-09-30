"""Informes breves para el equipo, a partir del estado persistido de Bruno."""

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func

from app.core.config import settings
from app.db.session_store import InformeDiario, OportunidadComercial, Sesion, SessionSesiones, UsoIA


PANAMA = ZoneInfo("America/Panama")


def usuarios_informes() -> set[str]:
    usuarios = json.loads(settings.CUBICO_TEAM_REPORT_USERS_JSON)
    if not isinstance(usuarios, list) or any(not isinstance(u, str) or not u.strip() for u in usuarios):
        raise ValueError("Destinatarios de informes inválidos")
    return {u.strip() for u in usuarios}


def _serializar_informe(fila) -> dict:
    return {"id": fila.id, "tipo": fila.tipo, "contenido": fila.contenido,
            "creado_en": fila.creado_en.isoformat() + "Z"}


def guardar_informe(tipo: str, contenido: str) -> tuple[dict, bool]:
    clave = datetime.now(PANAMA).strftime("%Y-%m-%d") + ":" + tipo
    with SessionSesiones() as db:
        anterior = db.query(InformeDiario).filter(InformeDiario.clave == clave).first()
        if anterior:
            return _serializar_informe(anterior), False
        fila = InformeDiario(clave=clave, tipo=tipo, contenido=contenido)
        db.add(fila)
        db.commit()
        return _serializar_informe(fila), True


def listar_informes() -> list[dict]:
    with SessionSesiones() as db:
        return [_serializar_informe(f) for f in db.query(InformeDiario).order_by(InformeDiario.id.desc()).limit(30)]


def _inicio_hoy_utc() -> datetime:
    hoy = datetime.now(PANAMA).replace(hour=0, minute=0, second=0, microsecond=0)
    return hoy.astimezone(timezone.utc).replace(tzinfo=None)


def _actividad_cliente_hoy(sesion, inicio: datetime) -> bool:
    # Una nota del operador o un aviso automático no son mensajes recibidos.
    for mensaje in sesion.obtener_historial():
        if mensaje.get("role") != "user" or not mensaje.get("timestamp"):
            continue
        try:
            fecha = datetime.fromisoformat(mensaje["timestamp"].replace("Z", "+00:00"))
            if fecha.tzinfo:
                fecha = fecha.astimezone(timezone.utc).replace(tzinfo=None)
            if fecha >= inicio:
                return True
        except (ValueError, TypeError, AttributeError):
            continue
    return False


def datos_informe() -> dict:
    """Cuenta actividad de hoy y pendientes actuales; no mezcla ambas métricas."""
    db = SessionSesiones()
    try:
        inicio = _inicio_hoy_utc()
        sesiones = db.query(Sesion).all()
        costo = db.query(func.coalesce(func.sum(UsoIA.costo_usd), 0)).filter(UsoIA.creado_en >= inicio).scalar()
        nuevas = db.query(OportunidadComercial).filter(OportunidadComercial.creada_en >= inicio).count()
        return {
            "conversaciones_hoy": sum(_actividad_cliente_hoy(s, inicio) for s in sesiones),
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
        f"Conexión de Bruno: {estado_api}. Conversaciones: disponibles.\n"
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
