import json
import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import settings
from app.db.session_store import listar_todas_sesiones, obtener_sesion_existente
from app.tools.clientes import obtener_nombre_completo_cliente

router = APIRouter(prefix="/panel", tags=["panel"])

TIMEZONE_PANAMA = ZoneInfo("America/Panama")

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
            "ultimo_mensaje": ultimo_mensaje,
            "tiene_no_leidos": (
                sesion.actualizado_en > sesion.ultimo_leido_panel
                if sesion.ultimo_leido_panel else True
            ),
        })
    return resultado


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


from app.ai.orchestrator import redactar_respuesta_de_asesor
from app.db.session_store import actualizar_sesion, agregar_al_historial
from app.api.whatsapp import enviar_respuesta_natural
import asyncio

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

    texto_redactado = redactar_respuesta_de_asesor(texto_cliente_original, mensaje)

    agregar_al_historial(telefono, "assistant", texto_redactado)
    await enviar_respuesta_natural(telefono, texto_redactado, message_id="")

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
    if sesion:
        actualizar_sesion(telefono, atencion_humana_directa=(accion == "tomar"))
    return {"status": "ok", "control": accion == "tomar"}

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
    await enviar_mensaje_whatsapp(telefono, mensaje)
    agregar_al_historial(telefono, "humano", mensaje)
    return {"status": "enviado"}


@router.get("/resumen")
def obtener_resumen(usuario: str = Depends(verificar_credenciales_panel)):
    """
    Contadores generales para las tarjetas de resumen del panel.
    "Hoy" se calcula en America/Panama, no en UTC (el servidor corre
    en UTC pero el negocio opera en hora de Panamá).
    """
    from app.db.session_store import contar_sesiones

    ahora_panama = datetime.now(TIMEZONE_PANAMA)
    inicio_dia_panama = ahora_panama.replace(hour=0, minute=0, second=0, microsecond=0)
    inicio_dia_utc = inicio_dia_panama.astimezone(timezone.utc).replace(tzinfo=None)

    return {
        "conversaciones_hoy": contar_sesiones(actualizado_desde=inicio_dia_utc),
        "requieren_humano": contar_sesiones(necesita_atencion_humana=True),
        "solicitudes_retiro": contar_sesiones(aviso_retiro_pendiente=True),
        "solicitudes_domicilio": contar_sesiones(solicitud_domicilio_pendiente=True),
    }


@router.get("/solicitudes")
def listar_solicitudes(usuario: str = Depends(verificar_credenciales_panel)):
    """
    Sesiones con un retiro o una entrega a domicilio pendiente, para
    la cola de solicitudes operativas del panel.
    """
    from app.db.session_store import (
        listar_sesiones_con_retiro_pendiente,
        listar_sesiones_con_domicilio_pendiente,
    )

    def _nombre_de(sesion):
        if sesion.codigo_cliente_verificado:
            info = obtener_nombre_completo_cliente(sesion.codigo_cliente_verificado)
            if info.get("encontrado"):
                return info["nombre_completo"]
        return sesion.telefono

    resultado = []
    for sesion in listar_sesiones_con_retiro_pendiente():
        resultado.append({
            "telefono": sesion.telefono,
            "nombre": _nombre_de(sesion),
            "tipo": "retiro",
            "necesita_atencion_humana": sesion.necesita_atencion_humana,
            "motivo_escalamiento": sesion.motivo_escalamiento or None,
        })
    for sesion in listar_sesiones_con_domicilio_pendiente():
        resultado.append({
            "telefono": sesion.telefono,
            "nombre": _nombre_de(sesion),
            "tipo": "domicilio",
            "necesita_atencion_humana": sesion.necesita_atencion_humana,
            "motivo_escalamiento": sesion.motivo_escalamiento or None,
        })
    return resultado


@router.get("/uso")
def obtener_uso(dias: int = 30, usuario: str = Depends(verificar_credenciales_panel)):
    """
    Uso y costo de la API de IA. Todavía no se registra el consumo de
    tokens por conversación, así que devuelve ceros y listas vacías.
    """
    return {
        "costo_usd": 0.0,
        "tokens_totales": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "conversaciones": 0,
        "llamadas": 0,
        "dias": [],
        "chats": [],
    }


@router.get("/comprobante/{telefono}")
def obtener_comprobante(telefono: str, usuario: str = Depends(verificar_credenciales_panel)):
    """
    Todavía no se guardan los comprobantes de pago recibidos por
    WhatsApp, así que este endpoint siempre responde que no hay uno
    disponible.
    """
    raise HTTPException(status_code=404, detail="Sin comprobante disponible")


@router.post("/solicitud/{telefono}/estado")
def actualizar_estado_solicitud(
    telefono: str,
    body: dict,
    usuario: str = Depends(verificar_credenciales_panel),
):
    """
    Avanza el flujo operativo de una solicitud de retiro/domicilio.
    Por ahora solo "Caso entregado y cerrado" tiene efecto real (limpia
    los avisos pendientes); las demás acciones son pasos intermedios
    que este backend todavía no rastrea con estado propio.
    """
    accion = body.get("accion", "")
    if accion == "Caso entregado y cerrado":
        actualizar_sesion(
            telefono,
            aviso_retiro_pendiente=False,
            solicitud_domicilio_pendiente=False,
        )
    return {"ok": True, "accion": accion}
