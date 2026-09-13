import asyncio
import json
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import settings
from app.db.session_store import (
    listar_todas_sesiones,
    obtener_sesion_existente,
    obtener_uso_por_telefono,
    obtener_resumen_uso,
    actualizar_sesion,
    agregar_al_historial,
)
from app.tools.clientes import obtener_nombre_completo_cliente
from app.tools.comprobantes import descargar_imagen_de_whatsapp
from app.tools.facturas import consultar_facturas_por_codigo
from app.ai.orchestrator import redactar_respuesta_de_asesor
from app.api.whatsapp import enviar_respuesta_natural

router = APIRouter(prefix="/panel", tags=["panel"])

security = HTTPBasic()

# Usuarios del panel: se cargan desde la variable de entorno
# PANEL_USUARIOS_JSON (un objeto JSON usuario -> contraseña). Nunca
# hardcodear usuarios/contraseñas reales aquí en el código.
USUARIOS_PANEL: dict[str, str] = json.loads(settings.PANEL_USUARIOS_JSON)


def verificar_credenciales_panel(credenciales: HTTPBasicCredentials = Depends(security)) -> str:
    """
    Busca al usuario en USUARIOS_PANEL (cargado desde PANEL_USUARIOS_JSON)
    y compara su contraseña con secrets.compare_digest para evitar
    timing attacks, en vez de una comparación directa con ==.
    """
    contrasena_esperada = USUARIOS_PANEL.get(credenciales.username)
    usuario_existe = contrasena_esperada is not None
    contrasena_correcta = secrets.compare_digest(
        credenciales.password, contrasena_esperada or ""
    )
    if not (usuario_existe and contrasena_correcta):
        raise HTTPException(
            status_code=401,
            detail="Credenciales inválidas",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credenciales.username


@router.get("/conversaciones")
def listar_conversaciones(usuario: str = Depends(verificar_credenciales_panel)):
    """
    Vista general: las conversaciones más recientes con su último
    mensaje, para el panel tipo "cámaras de seguridad".
    """
    resultado = []
    for sesion in listar_todas_sesiones():
        nombre = None
        if sesion.codigo_cliente_verificado:
            info = obtener_nombre_completo_cliente(sesion.codigo_cliente_verificado)
            if info.get("encontrado"):
                nombre = info["nombre_completo"]

        historial = sesion.obtener_historial()
        ultimo_mensaje = None
        if historial:
            ultimo = historial[-1]
            ultimo_mensaje = {"rol": ultimo.get("role"), "contenido": ultimo.get("content")}

        resultado.append({
            "telefono": sesion.telefono,
            "nombre": nombre,
            "codigo_cliente_verificado": sesion.codigo_cliente_verificado,
            "estado": sesion.estado,
            "necesita_atencion_humana": sesion.necesita_atencion_humana,
            "aviso_retiro_pendiente": sesion.aviso_retiro_pendiente,
            "solicitud_domicilio_pendiente": sesion.solicitud_domicilio_pendiente,
            "motivo_escalamiento": sesion.motivo_escalamiento or None,
            "atencion_humana_directa": bool(sesion.atencion_humana_directa),
            "actualizado_en": sesion.actualizado_en.isoformat() + "Z" if sesion.actualizado_en else None,
            "paquetes_a_retirar": sesion.paquetes_a_retirar,
            "direccion_domicilio": sesion.direccion_domicilio,
            "paquetes_a_domicilio": sesion.paquetes_a_domicilio,
            "pago_reportado": bool(sesion.pago_reportado),
            "pago_confirmado": bool(sesion.pago_confirmado),
            "paquetes_preparados": bool(sesion.paquetes_preparados),
            "domicilio_coordinado": bool(sesion.domicilio_coordinado),
            "entregado": bool(sesion.entregado),
            "metodo_pago_reportado": sesion.metodo_pago_reportado,
            "monto_pago_reportado": sesion.monto_pago_reportado,
            "uso": obtener_uso_por_telefono(sesion.telefono),
            "ultimo_mensaje": ultimo_mensaje,
            "tiene_no_leidos": (
                sesion.actualizado_en > sesion.ultimo_leido_panel
                if sesion.ultimo_leido_panel else True
            ),
        })
    return resultado


@router.get("/resumen")
def obtener_resumen_panel(usuario: str = Depends(verificar_credenciales_panel)):
    """Métricas reales usadas por el inicio del panel."""
    sesiones = listar_todas_sesiones(limite=500)
    inicio_hoy = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    uso = obtener_resumen_uso(30)
    activas_hoy = [s for s in sesiones if s.actualizado_en and s.actualizado_en >= inicio_hoy]
    solicitudes = [
        s for s in sesiones
        if (s.aviso_retiro_pendiente or s.solicitud_domicilio_pendiente) and not s.entregado
    ]
    return {
        "conversaciones_hoy": len(activas_hoy),
        "atencion_humana": sum(1 for s in sesiones if s.necesita_atencion_humana),
        "retiros": sum(1 for s in solicitudes if s.aviso_retiro_pendiente),
        "domicilios": sum(1 for s in solicitudes if s.solicitud_domicilio_pendiente),
        "pagos_por_confirmar": sum(1 for s in solicitudes if s.pago_reportado and not s.pago_confirmado),
        "listos": sum(1 for s in solicitudes if s.paquetes_preparados and not s.entregado),
        "costo_ia_30_dias": uso["costo_usd"],
        "tokens_30_dias": uso["tokens_totales"],
    }


def _nombre_cliente(sesion) -> str | None:
    if not sesion.codigo_cliente_verificado:
        return None
    try:
        info = obtener_nombre_completo_cliente(sesion.codigo_cliente_verificado)
        return info.get("nombre_completo") if info.get("encontrado") else None
    except Exception:
        return None


@router.get("/solicitudes")
def listar_solicitudes(usuario: str = Depends(verificar_credenciales_panel)):
    """Retiros y domicilios generados por conversaciones de WhatsApp."""
    solicitudes = []
    for sesion in listar_todas_sesiones(limite=500):
        if sesion.entregado:
            continue
        tipos = []
        if sesion.aviso_retiro_pendiente:
            tipos.append("retiro")
        if sesion.solicitud_domicilio_pendiente:
            tipos.append("domicilio")
        for tipo in tipos:
            monto_pendiente = None
            if sesion.codigo_cliente_verificado:
                try:
                    facturas = consultar_facturas_por_codigo(sesion.codigo_cliente_verificado)
                    monto_pendiente = facturas.get("saldo_pendiente_total") if facturas.get("encontrado") else None
                except Exception:
                    monto_pendiente = None
            solicitudes.append({
                "telefono": sesion.telefono,
                "nombre": _nombre_cliente(sesion) or sesion.telefono,
                "codigo_cliente": sesion.codigo_cliente_verificado,
                "tipo": tipo,
                "paquetes": sesion.paquetes_a_retirar if tipo == "retiro" else sesion.paquetes_a_domicilio,
                "direccion": sesion.direccion_domicilio if tipo == "domicilio" else "Sucursal Cúbico",
                "monto_pendiente": monto_pendiente,
                "pago_reportado": bool(sesion.pago_reportado),
                "pago_confirmado": bool(sesion.pago_confirmado) or monto_pendiente == 0,
                "paquetes_preparados": bool(sesion.paquetes_preparados),
                "domicilio_coordinado": bool(sesion.domicilio_coordinado),
                "tiene_comprobante": bool(sesion.comprobante_media_id),
                "actualizado_en": (
                    (sesion.solicitud_actualizada_en or sesion.actualizado_en).isoformat() + "Z"
                    if (sesion.solicitud_actualizada_en or sesion.actualizado_en) else None
                ),
            })
    solicitudes.sort(key=lambda item: item["actualizado_en"] or "", reverse=True)
    return solicitudes


@router.post("/solicitud/{telefono}/estado")
def actualizar_estado_solicitud(
    telefono: str,
    body: dict,
    usuario: str = Depends(verificar_credenciales_panel),
):
    """Avanza un retiro o domicilio sin crear registros duplicados."""
    sesion = obtener_sesion_existente(telefono)
    if sesion is None:
        raise HTTPException(status_code=404, detail="No existe esa conversación")
    accion = body.get("accion")
    tipo = body.get("tipo")
    if tipo not in {"retiro", "domicilio"}:
        raise HTTPException(status_code=400, detail="Tipo de solicitud inválido")

    if accion == "confirmar_pago":
        cambios = {"pago_confirmado": True}
    elif accion == "preparar":
        cambios = {"paquetes_preparados": True}
    elif accion == "coordinar" and tipo == "domicilio":
        cambios = {"domicilio_coordinado": True}
    elif accion == "entregar":
        cambios = {
            "entregado": True,
            "aviso_retiro_pendiente": False if tipo == "retiro" else sesion.aviso_retiro_pendiente,
            "solicitud_domicilio_pendiente": False if tipo == "domicilio" else sesion.solicitud_domicilio_pendiente,
        }
    else:
        raise HTTPException(status_code=400, detail="Acción inválida")

    actualizar_sesion(telefono, **cambios)
    return {"status": "ok", "accion": accion, "tipo": tipo}


@router.get("/uso")
def obtener_uso_panel(
    dias: int = 30,
    usuario: str = Depends(verificar_credenciales_panel),
):
    return obtener_resumen_uso(dias)


@router.get("/comprobante/{telefono}")
async def obtener_comprobante(
    telefono: str,
    usuario: str = Depends(verificar_credenciales_panel),
):
    """Entrega al operador el último comprobante sin exponer el token de Meta."""
    sesion = obtener_sesion_existente(telefono)
    if sesion is None or not sesion.comprobante_media_id:
        raise HTTPException(status_code=404, detail="No hay comprobante disponible")
    try:
        contenido = await descargar_imagen_de_whatsapp(sesion.comprobante_media_id)
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="Meta ya no permitió descargar ese comprobante; pide al cliente que lo reenvíe",
        ) from error
    return Response(content=contenido, media_type="image/jpeg")


@router.get("/conversacion/{telefono}")
def obtener_conversacion(telefono: str, usuario: str = Depends(verificar_credenciales_panel)):
    """Historial completo de una conversación específica."""
    sesion = obtener_sesion_existente(telefono)
    if sesion is None:
        raise HTTPException(status_code=404, detail="No existe ninguna conversación con ese teléfono")

    return {
        "telefono": sesion.telefono,
        "historial": sesion.obtener_historial(),
    }


@router.post("/responder/{telefono}")
async def responder_cliente(
    telefono: str,
    body: dict,
    usuario: str = Depends(verificar_credenciales_panel)
):
    """
    Envía una respuesta al cliente pasando por el flujo de Bruno,
    redactando el mensaje del asesor con su tono natural.

    A diferencia del flujo de /responder por WhatsApp (que requiere un
    caso escalado activo), el panel puede responder a cualquier
    conversación existente, esté o no escalada.
    """
    mensaje = body.get("mensaje", "").strip()
    if not mensaje:
        raise HTTPException(status_code=400, detail="Mensaje vacío")

    sesion_cliente = obtener_sesion_existente(telefono)
    if sesion_cliente is None:
        raise HTTPException(status_code=404, detail="No existe ninguna conversación con ese teléfono")

    historial = sesion_cliente.obtener_historial()
    texto_cliente_original = next(
        (m["content"] for m in reversed(historial) if m["role"] == "user"),
        "el cliente escribió por WhatsApp",
    )

    texto_redactado = await asyncio.to_thread(
        redactar_respuesta_de_asesor, texto_cliente_original, mensaje
    )

    respuesta_meta = await enviar_respuesta_natural(telefono, texto_redactado, message_id="")
    if hasattr(respuesta_meta, "is_success") and not respuesta_meta.is_success:
        raise HTTPException(status_code=502, detail="Meta no pudo enviar el mensaje")
    agregar_al_historial(telefono, "assistant", texto_redactado)

    actualizar_sesion(telefono, necesita_atencion_humana=False, motivo_escalamiento=None)

    return {"status": "enviado"}

@router.post("/atender/{telefono}")
def marcar_atendido(
    telefono: str,
    usuario: str = Depends(verificar_credenciales_panel)
):
    """Marca una conversación como atendida (baja la alerta)."""
    actualizar_sesion(telefono, necesita_atencion_humana=False)
    return {"status": "atendido"}


@router.post("/marcar-leido/{telefono}")
def marcar_leido(
    telefono: str,
    usuario: str = Depends(verificar_credenciales_panel)
):
    """Marca la conversación como leída por el trabajador en el panel."""
    actualizar_sesion(telefono, ultimo_leido_panel=datetime.utcnow())
    return {"status": "leido"}


@router.post("/retiro/{telefono}")
def marcar_retiro_listo(
    telefono: str,
    usuario: str = Depends(verificar_credenciales_panel)
):
    """Marca como resuelto el aviso de retiro de paquetes en el local."""
    actualizar_sesion(telefono, aviso_retiro_pendiente=False)
    return {"status": "retiro_resuelto"}


@router.post("/domicilio/{telefono}")
def marcar_domicilio_coordinado(
    telefono: str,
    usuario: str = Depends(verificar_credenciales_panel)
):
    """Marca como resuelta la solicitud de entrega a domicilio."""
    actualizar_sesion(telefono, solicitud_domicilio_pendiente=False)
    return {"status": "domicilio_resuelto"}


@router.post("/control/{telefono}")
async def tomar_control(
    telefono: str,
    body: dict,
    usuario: str = Depends(verificar_credenciales_panel)
):
    from app.db.session_store import obtener_sesion_existente, actualizar_sesion
    accion = body.get("accion", "tomar")
    sesion = obtener_sesion_existente(telefono)
    if sesion is None:
        raise HTTPException(status_code=404, detail="No existe esa conversación")
    control_activo = accion == "tomar"
    actualizar_sesion(telefono, atencion_humana_directa=control_activo)
    return {"status": "ok", "control": control_activo}

@router.post("/enviar-directo/{telefono}")
async def enviar_directo(
    telefono: str,
    body: dict,
    usuario: str = Depends(verificar_credenciales_panel)
):
    from app.api.whatsapp import enviar_mensaje_whatsapp
    from app.db.session_store import agregar_al_historial
    mensaje = body.get("mensaje", "").strip()
    if not mensaje:
        raise HTTPException(status_code=400, detail="Mensaje vacío")
    respuesta_meta = await enviar_mensaje_whatsapp(telefono, mensaje)
    if not respuesta_meta.is_success:
        raise HTTPException(status_code=502, detail="Meta no pudo enviar el mensaje")
    agregar_al_historial(telefono, "humano", mensaje)
    return {"status": "enviado"}
