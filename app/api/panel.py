import asyncio
import json
import secrets
import shutil
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from app.core.config import settings
from app.db.session_store import (
    listar_todas_sesiones,
    obtener_sesion_existente,
    obtener_uso_por_telefono,
    obtener_resumen_uso,
    actualizar_sesion,
    agregar_al_historial,
    eliminar_suscripcion_push,
    guardar_suscripcion_push,
    listar_oportunidades_comerciales,
    actualizar_oportunidad_comercial,
)
from app.services.push_notifications import push_configurado
from app.tools.clientes import obtener_nombre_completo_cliente
from app.tools.comprobantes import descargar_imagen_de_whatsapp
from app.tools.transcripcion import descargar_audio_de_whatsapp
from app.tools.facturas import (
    consultar_facturas_por_codigo,
    registrar_pago_factura_desde_panel,
)
from app.ai.orchestrator import redactar_respuesta_de_asesor
from app.api.whatsapp import (
    enviar_audio_whatsapp,
    enviar_documento_whatsapp,
    enviar_imagen_whatsapp,
    enviar_respuesta_natural,
    extraer_id_mensaje_meta,
    subir_audio_whatsapp,
    subir_media_whatsapp,
)

router = APIRouter(prefix="/panel", tags=["panel"])

security = HTTPBasic()

# Usuarios del panel: se cargan desde la variable de entorno
# PANEL_USUARIOS_JSON (un objeto JSON usuario -> contraseña). Nunca
# hardcodear usuarios/contraseñas reales aquí en el código.
USUARIOS_PANEL: dict[str, str] = json.loads(settings.PANEL_USUARIOS_JSON)


class SuscripcionPushPayload(BaseModel):
    endpoint: str
    keys: dict[str, str]


class OportunidadPayload(BaseModel):
    estado: str | None = None
    nota: str | None = None
    tomar: bool = False


def _ultimo_mensaje_cliente_en(historial: list[dict]) -> datetime | None:
    """Fecha del último mensaje entrante; ignora respuestas y cambios operativos."""
    for mensaje in reversed(historial):
        if mensaje.get("role") != "user" or not mensaje.get("timestamp"):
            continue
        try:
            fecha = datetime.fromisoformat(str(mensaje["timestamp"]).replace("Z", "+00:00"))
            return fecha.replace(tzinfo=None)
        except (TypeError, ValueError):
            continue
    return None


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


def _validar_operador_conversacion(
    telefono: str,
    usuario: str,
    requiere_control: bool = False,
):
    """Impide respuestas cruzadas entre trabajadores con paneles desactualizados."""
    sesion = obtener_sesion_existente(telefono)
    if sesion is None:
        raise HTTPException(status_code=404, detail="No existe esa conversación")
    activa = bool(getattr(sesion, "atencion_humana_directa", False))
    operador = getattr(sesion, "atencion_humana_por", None)
    if activa and operador and operador != usuario:
        raise HTTPException(
            status_code=409,
            detail=f"Esta conversación está siendo atendida por {operador}.",
        )
    if requiere_control and (not activa or operador != usuario):
        raise HTTPException(
            status_code=409,
            detail="Debes tomar el control de esta conversación antes de enviar directamente.",
        )
    return sesion


@router.get("/push/config")
def configuracion_push(usuario: str = Depends(verificar_credenciales_panel)):
    return {
        "disponible": push_configurado(),
        "public_key": settings.PUSH_VAPID_PUBLIC_KEY if push_configurado() else "",
    }


@router.post("/push/suscripcion")
def registrar_push(
    payload: SuscripcionPushPayload,
    usuario: str = Depends(verificar_credenciales_panel),
):
    if not push_configurado():
        raise HTTPException(status_code=503, detail="Notificaciones push no configuradas")
    try:
        guardar_suscripcion_push(usuario, payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"ok": True}


@router.delete("/push/suscripcion")
def borrar_push(
    payload: SuscripcionPushPayload,
    usuario: str = Depends(verificar_credenciales_panel),
):
    return {"ok": True, "eliminada": eliminar_suscripcion_push(payload.endpoint)}


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
        ultimo_mensaje_cliente = None
        if historial:
            ultimo = historial[-1]
            ultimo_mensaje = {
                "rol": ultimo.get("role"),
                "contenido": ultimo.get("content"),
                "timestamp": ultimo.get("timestamp"),
                "id": ultimo.get("whatsapp_message_id"),
                "estado_entrega": ultimo.get("estado_entrega"),
                "error_entrega": ultimo.get("error_entrega"),
            }
            ultimo_cliente = next(
                (mensaje for mensaje in reversed(historial) if mensaje.get("role") == "user"),
                None,
            )
            if ultimo_cliente:
                ultimo_mensaje_cliente = {
                    "contenido": ultimo_cliente.get("content"),
                    "timestamp": ultimo_cliente.get("timestamp"),
                    "id": ultimo_cliente.get("whatsapp_message_id"),
                }
        ultimo_cliente_en = _ultimo_mensaje_cliente_en(historial)

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
            "atencion_humana_por": sesion.atencion_humana_por,
            "atencion_humana_desde": (
                sesion.atencion_humana_desde.isoformat() + "Z"
                if sesion.atencion_humana_desde else None
            ),
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
            "ultimo_mensaje_cliente": ultimo_mensaje_cliente,
            "tiene_no_leidos": bool(
                ultimo_cliente_en
                and (
                    sesion.ultimo_leido_panel is None
                    or ultimo_cliente_en > sesion.ultimo_leido_panel
                )
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
    oportunidades = listar_oportunidades_comerciales()
    return {
        "conversaciones_hoy": len(activas_hoy),
        "atencion_humana": sum(1 for s in sesiones if s.necesita_atencion_humana),
        "retiros": sum(1 for s in solicitudes if s.aviso_retiro_pendiente),
        "domicilios": sum(1 for s in solicitudes if s.solicitud_domicilio_pendiente),
        "pagos_por_confirmar": sum(
            1 for s in sesiones if s.pago_reportado and not s.pago_confirmado
        ),
        "listos": sum(1 for s in solicitudes if s.paquetes_preparados and not s.entregado),
        "oportunidades_nuevas": sum(
            1 for oportunidad in oportunidades
            if oportunidad["estado"] == "nueva"
        ),
        "oportunidades_activas": sum(
            1 for oportunidad in oportunidades
            if oportunidad["estado"] not in {"ganada", "no_concretada"}
        ),
        "costo_ia_30_dias": uso["costo_usd"],
        "tokens_30_dias": uso["tokens_totales"],
    }


@router.get("/oportunidades")
def obtener_oportunidades_panel(usuario: str = Depends(verificar_credenciales_panel)):
    """Bandeja comercial resumida; no genera ni decide tarifas."""
    return listar_oportunidades_comerciales()


@router.post("/oportunidad/{oportunidad_id}")
def modificar_oportunidad_panel(
    oportunidad_id: int,
    payload: OportunidadPayload,
    usuario: str = Depends(verificar_credenciales_panel),
):
    oportunidades = listar_oportunidades_comerciales()
    oportunidad = next(
        (item for item in oportunidades if item["id"] == oportunidad_id),
        None,
    )
    if oportunidad is None:
        raise HTTPException(status_code=404, detail="La oportunidad no existe")
    asignado = oportunidad.get("asignado_a")
    if asignado and asignado != usuario:
        raise HTTPException(
            status_code=409,
            detail=f"Esta oportunidad está siendo revisada por {asignado}.",
        )
    nuevo_estado = payload.estado
    if payload.tomar and nuevo_estado is None and oportunidad["estado"] == "nueva":
        nuevo_estado = "en_revision"
    try:
        return actualizar_oportunidad_comercial(
            oportunidad_id,
            estado=nuevo_estado,
            asignado_a=usuario if payload.tomar or nuevo_estado or payload.nota else None,
            nota=payload.nota,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/actividad")
def listar_actividad_panel(usuario: str = Depends(verificar_credenciales_panel)):
    """Polling liviano para mensajes nuevos, no leídos y control humano."""
    actividad = []
    for sesion in listar_todas_sesiones(limite=100):
        historial = sesion.obtener_historial()
        ultimo = historial[-1] if historial else None
        ultimo_cliente = next(
            (mensaje for mensaje in reversed(historial) if mensaje.get("role") == "user"),
            None,
        )
        ultimo_cliente_en = _ultimo_mensaje_cliente_en(historial)
        actividad.append({
            "telefono": sesion.telefono,
            "actualizado_en": (
                sesion.actualizado_en.isoformat() + "Z" if sesion.actualizado_en else None
            ),
            "necesita_atencion_humana": bool(sesion.necesita_atencion_humana),
            "motivo_escalamiento": sesion.motivo_escalamiento or None,
            "atencion_humana_directa": bool(sesion.atencion_humana_directa),
            "atencion_humana_por": sesion.atencion_humana_por,
            "atencion_humana_desde": (
                sesion.atencion_humana_desde.isoformat() + "Z"
                if sesion.atencion_humana_desde else None
            ),
            "ultimo_mensaje": ({
                "rol": ultimo.get("role"),
                "contenido": ultimo.get("content"),
                "timestamp": ultimo.get("timestamp"),
                "id": ultimo.get("whatsapp_message_id"),
                "estado_entrega": ultimo.get("estado_entrega"),
                "error_entrega": ultimo.get("error_entrega"),
            } if ultimo else None),
            "ultimo_mensaje_cliente": ({
                "contenido": ultimo_cliente.get("content"),
                "timestamp": ultimo_cliente.get("timestamp"),
                "id": ultimo_cliente.get("whatsapp_message_id"),
            } if ultimo_cliente else None),
            "tiene_no_leidos": bool(
                ultimo_cliente_en
                and (
                    sesion.ultimo_leido_panel is None
                    or ultimo_cliente_en > sesion.ultimo_leido_panel
                )
            ),
        })
    return actividad


def _nombre_cliente(sesion) -> str | None:
    if not sesion.codigo_cliente_verificado:
        return None
    try:
        info = obtener_nombre_completo_cliente(sesion.codigo_cliente_verificado)
        return info.get("nombre_completo") if info.get("encontrado") else None
    except Exception:
        return None


def _exigir_factura_pagada(sesion) -> dict:
    """Bloquea la preparación/entrega si no existe una factura saldada."""
    if not sesion.codigo_cliente_verificado:
        raise HTTPException(
            status_code=409,
            detail="Primero debe verificarse el cliente y asociarse una factura",
        )
    try:
        facturas = consultar_facturas_por_codigo(sesion.codigo_cliente_verificado)
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="No se pudo comprobar el estado del pago en facturación",
        ) from error
    if not facturas.get("encontrado") or facturas.get("cantidad_facturas", 0) < 1:
        raise HTTPException(
            status_code=409,
            detail="No se puede continuar: el cliente todavía no tiene una factura asociada",
        )
    if float(facturas.get("saldo_pendiente_total") or 0) > .01:
        raise HTTPException(
            status_code=409,
            detail="Aún existe saldo pendiente; primero debe confirmarse el pago",
        )
    return facturas


@router.get("/solicitudes")
def listar_solicitudes(usuario: str = Depends(verificar_credenciales_panel)):
    """Retiros, domicilios y comprobantes generados desde WhatsApp."""
    solicitudes = []
    for sesion in listar_todas_sesiones(limite=500):
        comprobante_pendiente = bool(sesion.pago_reportado and not sesion.pago_confirmado)
        if sesion.entregado and not comprobante_pendiente:
            continue
        tipos = []
        if sesion.aviso_retiro_pendiente:
            tipos.append("retiro")
        if sesion.solicitud_domicilio_pendiente:
            tipos.append("domicilio")
        # Un comprobante siempre debe llegar a la cola. Si ya existe un
        # retiro/domicilio se integra allí; si no, crea un caso exclusivo
        # de pago para que ningún operador lo pierda.
        if comprobante_pendiente and not tipos:
            tipos.append("pago")
        for tipo in tipos:
            monto_pendiente = None
            pago_confirmado_sistema = False
            detalle_facturas = []
            factura_sugerida = None
            tiene_facturas = False
            if sesion.codigo_cliente_verificado:
                try:
                    facturas = consultar_facturas_por_codigo(sesion.codigo_cliente_verificado)
                    tiene_facturas = bool(
                        facturas.get("encontrado")
                        and facturas.get("cantidad_facturas", 0) > 0
                    )
                    if tiene_facturas:
                        monto_pendiente = facturas.get("saldo_pendiente_total")
                        pago_confirmado_sistema = float(monto_pendiente or 0) <= .01
                        detalle_facturas = [
                            factura for factura in facturas.get("facturas", [])
                            if factura.get("saldo_pendiente", 0) > 0
                        ]
                        monto_reportado = sesion.monto_pago_reportado
                        coincidencias = [
                            factura for factura in detalle_facturas
                            if monto_reportado is not None
                            and abs(float(factura["saldo_pendiente"]) - float(monto_reportado)) < .005
                        ]
                        if len(coincidencias) == 1:
                            factura_sugerida = coincidencias[0]["codigo"]
                        elif len(detalle_facturas) == 1:
                            factura_sugerida = detalle_facturas[0]["codigo"]
                except Exception:
                    monto_pendiente = None
            pago_confirmado_panel = bool(sesion.pago_confirmado)
            paquetes_factura = [
                paquete.get("tracking")
                for factura in detalle_facturas
                for paquete in factura.get("paquetes", [])
                if paquete.get("tracking")
            ]
            if tipo == "retiro":
                detalle_paquetes = sesion.paquetes_a_retirar
                direccion = "Sucursal Cúbico"
            elif tipo == "domicilio":
                detalle_paquetes = sesion.paquetes_a_domicilio
                direccion = sesion.direccion_domicilio
            else:
                detalle_paquetes = ", ".join(paquetes_factura) or "Comprobante recibido por WhatsApp"
                direccion = "No aplica"

            solicitudes.append({
                "telefono": sesion.telefono,
                "nombre": _nombre_cliente(sesion) or sesion.telefono,
                "codigo_cliente": sesion.codigo_cliente_verificado,
                "tipo": tipo,
                "paquetes": detalle_paquetes,
                "direccion": direccion,
                "monto_pendiente": monto_pendiente,
                "monto_reportado": sesion.monto_pago_reportado,
                "metodo_reportado": sesion.metodo_pago_reportado,
                "referencia_reportada": sesion.referencia_pago_reportado,
                "fecha_reportada": sesion.fecha_pago_reportado,
                "diferencia_pago": (
                    round(float(sesion.monto_pago_reportado) - float(monto_pendiente), 2)
                    if sesion.monto_pago_reportado is not None and monto_pendiente is not None
                    else None
                ),
                "facturas_pendientes": detalle_facturas,
                "factura_sugerida": factura_sugerida,
                "pago_reportado": bool(sesion.pago_reportado),
                "pago_confirmado": pago_confirmado_panel,
                "pago_confirmado_sistema": pago_confirmado_sistema,
                "requiere_factura": tipo != "pago" and not tiene_facturas,
                "pago_resuelto": (
                    pago_confirmado_sistema
                    if tipo != "pago"
                    else pago_confirmado_sistema or pago_confirmado_panel
                ),
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
    if tipo not in {"retiro", "domicilio", "pago"}:
        raise HTTPException(status_code=400, detail="Tipo de solicitud inválido")
    if tipo == "pago" and accion != "confirmar_pago":
        raise HTTPException(status_code=400, detail="Este caso solamente permite confirmar el pago")

    if accion == "confirmar_pago":
        if sesion.pago_confirmado:
            raise HTTPException(status_code=409, detail="Este comprobante ya fue procesado")
        resultado_pago = None
        if sesion.codigo_cliente_verificado:
            facturas = consultar_facturas_por_codigo(sesion.codigo_cliente_verificado)
            pendientes = [
                factura for factura in facturas.get("facturas", [])
                if factura.get("saldo_pendiente", 0) > 0
            ]
            if pendientes:
                if not sesion.pago_reportado or sesion.monto_pago_reportado is None:
                    raise HTTPException(
                        status_code=409,
                        detail="Primero debe existir un comprobante con monto legible",
                    )
                codigo_factura = body.get("factura_codigo")
                if not codigo_factura:
                    coincidencias = [
                        factura for factura in pendientes
                        if abs(float(factura["saldo_pendiente"]) - float(sesion.monto_pago_reportado)) < .005
                    ]
                    if len(coincidencias) == 1:
                        codigo_factura = coincidencias[0]["codigo"]
                    elif len(pendientes) == 1:
                        codigo_factura = pendientes[0]["codigo"]
                    else:
                        raise HTTPException(
                            status_code=409,
                            detail="Selecciona la factura a la que corresponde el comprobante",
                        )
                try:
                    resultado_pago = registrar_pago_factura_desde_panel(
                        sesion.codigo_cliente_verificado,
                        codigo_factura,
                        sesion.monto_pago_reportado,
                        sesion.metodo_pago_reportado,
                        sesion.referencia_pago_reportado,
                        sesion.fecha_pago_reportado,
                    )
                except ValueError as error:
                    raise HTTPException(status_code=409, detail=str(error)) from error
                except Exception as error:
                    raise HTTPException(
                        status_code=502,
                        detail="No se pudo registrar el pago en facturación",
                    ) from error
            elif tipo != "pago":
                raise HTTPException(
                    status_code=409,
                    detail="No se puede confirmar para esta entrega: falta una factura asociada",
                )
        elif tipo != "pago":
            raise HTTPException(
                status_code=409,
                detail="Primero debe verificarse el cliente y asociarse una factura",
            )
        cambios = {"pago_confirmado": True}
    elif accion == "preparar":
        _exigir_factura_pagada(sesion)
        cambios = {"paquetes_preparados": True}
    elif accion == "coordinar" and tipo == "domicilio":
        _exigir_factura_pagada(sesion)
        if not sesion.paquetes_preparados:
            raise HTTPException(status_code=409, detail="Primero marca los paquetes como listos")
        cambios = {"domicilio_coordinado": True}
    elif accion == "entregar":
        _exigir_factura_pagada(sesion)
        if not sesion.paquetes_preparados:
            raise HTTPException(status_code=409, detail="Primero marca los paquetes como listos")
        if tipo == "domicilio" and not sesion.domicilio_coordinado:
            raise HTTPException(status_code=409, detail="Primero coordina el domicilio")
        cambios = {
            "entregado": True,
            "aviso_retiro_pendiente": False if tipo == "retiro" else sesion.aviso_retiro_pendiente,
            "solicitud_domicilio_pendiente": False if tipo == "domicilio" else sesion.solicitud_domicilio_pendiente,
        }
    else:
        raise HTTPException(status_code=400, detail="Acción inválida")

    actualizar_sesion(telefono, **cambios)
    respuesta = {"status": "ok", "accion": accion, "tipo": tipo}
    if accion == "confirmar_pago":
        respuesta["pago"] = resultado_pago
    return respuesta


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


@router.get("/imagen/{telefono}/{media_id}")
async def obtener_imagen_panel(
    telefono: str,
    media_id: str,
    usuario: str = Depends(verificar_credenciales_panel),
):
    """Sirve una imagen que realmente pertenece al historial del cliente."""
    sesion = obtener_sesion_existente(telefono)
    if sesion is None:
        raise HTTPException(status_code=404, detail="No existe esa conversación")
    pertenece = sesion.comprobante_media_id == media_id or any(
        item.get("tipo") == "image" and item.get("media_id") == media_id
        for item in sesion.obtener_historial()
    )
    if not pertenece:
        raise HTTPException(status_code=404, detail="Esa imagen no pertenece a la conversación")
    try:
        contenido = await descargar_imagen_de_whatsapp(media_id)
    except Exception as error:
        raise HTTPException(status_code=502, detail="Meta ya no permitió descargar esta imagen") from error
    return Response(
        content=contenido,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=60"},
    )


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


@router.get("/audio/{telefono}/{media_id}")
async def obtener_audio_panel(
    telefono: str,
    media_id: str,
    usuario: str = Depends(verificar_credenciales_panel),
):
    """Sirve un audio del historial sin exponer el token privado de Meta."""
    sesion = obtener_sesion_existente(telefono)
    if sesion is None:
        raise HTTPException(status_code=404, detail="No existe esa conversación")
    mensaje = next(
        (
            item for item in sesion.obtener_historial()
            if item.get("tipo") == "audio" and item.get("media_id") == media_id
        ),
        None,
    )
    if mensaje is None:
        raise HTTPException(status_code=404, detail="Ese audio no pertenece a la conversación")
    try:
        contenido = await descargar_audio_de_whatsapp(media_id)
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail="Meta ya no permitió descargar este audio",
        ) from error
    return Response(
        content=contenido,
        media_type=mensaje.get("mime_type") or "audio/ogg",
        headers={"Cache-Control": "private, max-age=60"},
    )


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
    _validar_operador_conversacion(telefono, usuario)

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
    agregar_al_historial(
        telefono,
        "assistant",
        texto_redactado,
        whatsapp_message_id=extraer_id_mensaje_meta(respuesta_meta),
        estado_entrega="accepted",
    )

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


async def _convertir_audio_webm_a_ogg(audio: bytes) -> bytes:
    """Convierte la grabación del navegador a OGG/Opus aceptado por WhatsApp."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise HTTPException(
            status_code=503,
            detail="El servidor todavía no tiene instalado el convertidor de audio",
        )
    proceso = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-fflags",
        "+genpts",
        "-i",
        "pipe:0",
        "-vn",
        "-map_metadata",
        "-1",
        "-af",
        "aresample=async=1:first_pts=0",
        "-ac",
        "1",
        "-ar",
        "48000",
        "-c:a",
        "libopus",
        "-b:a",
        "32k",
        "-application",
        "voip",
        "-avoid_negative_ts",
        "make_zero",
        "-f",
        "ogg",
        "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        salida, error = await asyncio.wait_for(proceso.communicate(audio), timeout=30)
    except TimeoutError as exc:
        proceso.kill()
        await proceso.wait()
        raise HTTPException(status_code=504, detail="La conversión del audio tardó demasiado") from exc
    if proceso.returncode != 0 or not salida:
        detalle = error.decode("utf-8", errors="ignore")[-300:]
        raise HTTPException(status_code=400, detail=f"No se pudo procesar la grabación: {detalle}")
    return salida


@router.post("/enviar-audio/{telefono}")
async def enviar_audio_desde_panel(
    telefono: str,
    request: Request,
    usuario: str = Depends(verificar_credenciales_panel),
):
    """Recibe una grabación del panel, la normaliza y la envía por WhatsApp."""
    _validar_operador_conversacion(telefono, usuario, requiere_control=True)
    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="La grabación está vacía")
    if len(audio) > 16 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="La grabación supera el límite de 16 MB")

    mime_original = request.headers.get("content-type", "").split(";", 1)[0].lower()
    formatos_grabacion = {
        "audio/ogg", "audio/webm", "video/webm", "application/octet-stream",
        "audio/mpeg", "audio/mp4", "audio/aac", "audio/amr",
    }
    if mime_original in formatos_grabacion:
        # El navegador puede grabar estéreo o usar marcas de tiempo que iOS
        # no reproduce bien. Normalizamos siempre a la variante exacta que
        # WhatsApp exige para notas de voz: OGG, Opus, mono y 48 kHz.
        audio_meta = await _convertir_audio_webm_a_ogg(audio)
        mime_meta = "audio/ogg; codecs=opus"
        extension = "ogg"
    else:
        raise HTTPException(status_code=415, detail="El navegador produjo un formato de audio no compatible")

    try:
        media_id = await subir_audio_whatsapp(
            audio_meta,
            mime_type=mime_meta,
            nombre_archivo=f"mensaje-voz.{extension}",
        )
        respuesta_envio = await enviar_audio_whatsapp(telefono, media_id)
    except (httpx.HTTPError, RuntimeError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    agregar_al_historial(
        telefono,
        "humano",
        "Nota de voz",
        tipo="audio",
        media_id=media_id,
        mime_type=mime_meta,
        whatsapp_message_id=extraer_id_mensaje_meta(respuesta_envio),
        estado_entrega="accepted",
    )
    return {"status": "enviado"}


TIPOS_ARCHIVO_PERMITIDOS = {
    "image": {"image/jpeg", "image/png"},
    "document": {"application/pdf"},
}


@router.post("/enviar-archivo/{telefono}")
async def enviar_archivo_desde_panel(
    telefono: str,
    tipo: str = Form(...),
    archivo: UploadFile = File(...),
    usuario: str = Depends(verificar_credenciales_panel),
):
    """Sube una imagen o un PDF a la Media API de Meta y lo envía al cliente."""
    _validar_operador_conversacion(telefono, usuario, requiere_control=True)
    if tipo not in TIPOS_ARCHIVO_PERMITIDOS:
        raise HTTPException(status_code=400, detail="Tipo de archivo inválido")

    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo está vacío")
    if len(contenido) > 16 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="El archivo supera el límite de 16 MB")

    mime_type = archivo.content_type or ""
    if mime_type not in TIPOS_ARCHIVO_PERMITIDOS[tipo]:
        raise HTTPException(
            status_code=415,
            detail="Formato de archivo no compatible (se acepta imagen JPG/PNG o PDF)",
        )

    try:
        media_id = await subir_media_whatsapp(
            contenido, mime_type=mime_type, nombre_archivo=archivo.filename or "archivo"
        )
        if tipo == "image":
            respuesta_envio = await enviar_imagen_whatsapp(telefono, media_id)
        else:
            respuesta_envio = await enviar_documento_whatsapp(telefono, media_id, nombre_archivo=archivo.filename)
    except (httpx.HTTPError, RuntimeError) as error:
        return {"ok": False, "motivo": str(error)}

    if not respuesta_envio.is_success:
        return {"ok": False, "motivo": "Meta no pudo enviar el archivo"}

    agregar_al_historial(
        telefono,
        "humano",
        f"[Archivo enviado: {archivo.filename}]",
        tipo=tipo,
        media_id=media_id,
        mime_type=mime_type,
        whatsapp_message_id=extraer_id_mensaje_meta(respuesta_envio),
        estado_entrega="accepted",
    )
    return {"ok": True}


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
    accion = body.get("accion", "tomar")
    if accion not in {"tomar", "devolver"}:
        raise HTTPException(status_code=400, detail="Acción de control inválida")
    sesion = obtener_sesion_existente(telefono)
    if sesion is None:
        raise HTTPException(status_code=404, detail="No existe esa conversación")
    control_activo = accion == "tomar"
    operador_actual = getattr(sesion, "atencion_humana_por", None)
    estaba_activo = bool(getattr(sesion, "atencion_humana_directa", False))
    forzar = bool(body.get("forzar", False))
    if control_activo and estaba_activo and operador_actual == usuario:
        return {"status": "ok", "control": True, "operador": usuario}
    if control_activo and estaba_activo and operador_actual and operador_actual != usuario and not forzar:
        raise HTTPException(
            status_code=409,
            detail=f"Esta conversación está siendo atendida por {operador_actual}.",
        )
    if not control_activo and estaba_activo and operador_actual and operador_actual != usuario:
        raise HTTPException(
            status_code=409,
            detail=f"Solo {operador_actual} puede devolver esta conversación a Bruno.",
        )
    actualizar_sesion(
        telefono,
        atencion_humana_directa=control_activo,
        atencion_humana_por=usuario if control_activo else None,
        atencion_humana_desde=datetime.utcnow() if control_activo else None,
    )
    return {
        "status": "ok",
        "control": control_activo,
        "operador": usuario if control_activo else None,
    }

@router.post("/enviar-directo/{telefono}")
async def enviar_directo(
    telefono: str,
    body: dict,
    usuario: str = Depends(verificar_credenciales_panel)
):
    from app.api.whatsapp import enviar_mensaje_whatsapp, extraer_id_mensaje_meta
    from app.db.session_store import agregar_al_historial
    mensaje = body.get("mensaje", "").strip()
    if not mensaje:
        raise HTTPException(status_code=400, detail="Mensaje vacío")
    _validar_operador_conversacion(telefono, usuario, requiere_control=True)
    respuesta_meta = await enviar_mensaje_whatsapp(telefono, mensaje)
    if not respuesta_meta.is_success:
        raise HTTPException(status_code=502, detail="Meta no pudo enviar el mensaje")
    agregar_al_historial(
        telefono,
        "humano",
        mensaje,
        whatsapp_message_id=extraer_id_mensaje_meta(respuesta_meta),
        estado_entrega="accepted",
    )
    return {"status": "enviado"}
