import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import settings
from app.db.session_store import listar_todas_sesiones, obtener_sesion_existente
from app.tools.clientes import obtener_nombre_completo_cliente

router = APIRouter(prefix="/panel", tags=["panel"])

security = HTTPBasic()


def verificar_credenciales_panel(credenciales: HTTPBasicCredentials = Depends(security)) -> str:
    """
    Compara usuario y contraseña con secrets.compare_digest para evitar
    timing attacks, en vez de una comparación directa con ==.
    """
    usuario_correcto = secrets.compare_digest(credenciales.username, settings.PANEL_USUARIO)
    contrasena_correcta = secrets.compare_digest(credenciales.password, settings.PANEL_CONTRASENA)
    if not (usuario_correcto and contrasena_correcta):
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
            "ultimo_mensaje": ultimo_mensaje,
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


from app.api.whatsapp import procesar_respuesta_de_asesor
from app.db.session_store import actualizar_sesion
import asyncio

@router.post("/responder/{telefono}")
async def responder_cliente(
    telefono: str,
    body: dict,
    usuario: str = Depends(verificar_credenciales_panel)
):
    """Envía una respuesta al cliente pasando por el flujo de Bruno."""
    mensaje = body.get("mensaje", "").strip()
    if not mensaje:
        raise HTTPException(status_code=400, detail="Mensaje vacío")
    await procesar_respuesta_de_asesor(
        telefono_asesor="panel",
        numero_cliente=telefono,
        solucion_del_asesor=mensaje
    )
    return {"status": "enviado"}

@router.post("/atender/{telefono}")
def marcar_atendido(
    telefono: str,
    usuario: str = Depends(verificar_credenciales_panel)
):
    """Marca una conversación como atendida (baja la alerta)."""
    actualizar_sesion(telefono, necesita_atencion_humana=False)
    return {"status": "atendido"}


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
