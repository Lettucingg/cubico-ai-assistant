import json

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Float, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime, timedelta

from app.core.config import settings

_session_database_url = settings.SESSION_DATABASE_URL
_engine_options = {"pool_pre_ping": True}
if _session_database_url.startswith("sqlite"):
    _engine_options["connect_args"] = {"check_same_thread": False}

engine_sesiones = create_engine(_session_database_url, **_engine_options)
SessionSesiones = sessionmaker(bind=engine_sesiones)
BaseSesiones = declarative_base()


class Sesion(BaseSesiones):
    """
    Representa el estado de la conversación con un número de
    teléfono específico, incluyendo el historial de mensajes
    recientes para que Claude tenga memoria de la conversación.
    """
    __tablename__ = "sesiones"

    id = Column(Integer, primary_key=True)
    telefono = Column(String, unique=True, nullable=False)
    estado = Column(String, default="esperando_codigo")
    codigo_cliente_temporal = Column(String, nullable=True)
    codigo_cliente_verificado = Column(String, nullable=True)
    historial_json = Column(Text, default="[]")
    necesita_atencion_humana = Column(Boolean, default=False)
    motivo_escalamiento = Column(Text, nullable=True)
    aviso_retiro_pendiente = Column(Boolean, default=False)
    paquetes_a_retirar = Column(Text, nullable=True)
    solicitud_domicilio_pendiente = Column(Boolean, default=False)
    direccion_domicilio = Column(Text, nullable=True)
    paquetes_a_domicilio = Column(Text, nullable=True)
    factura_pendiente_notificacion = Column(String, nullable=True)
    tipo_seguimiento_pago = Column(String, nullable=True)  # general | domicilio
    actualizado_en = Column(DateTime, default=datetime.utcnow)
    ultimo_leido_panel = Column(DateTime, nullable=True)
    atencion_humana_directa = Column(Boolean, default=False)
    atencion_humana_por = Column(String, nullable=True)
    atencion_humana_desde = Column(DateTime, nullable=True)
    pago_reportado = Column(Boolean, default=False)
    pago_confirmado = Column(Boolean, default=False)
    paquetes_preparados = Column(Boolean, default=False)
    domicilio_coordinado = Column(Boolean, default=False)
    entregado = Column(Boolean, default=False)
    metodo_pago_reportado = Column(String, nullable=True)
    monto_pago_reportado = Column(Float, nullable=True)
    referencia_pago_reportado = Column(String, nullable=True)
    fecha_pago_reportado = Column(String, nullable=True)
    comprobante_media_id = Column(String, nullable=True)
    solicitud_actualizada_en = Column(DateTime, nullable=True)

    def obtener_historial(self):
        """Convierte el historial guardado (texto JSON) en una lista de Python."""
        return json.loads(self.historial_json or "[]")


class UsoIA(BaseSesiones):
    """Una fila por llamada a Claude para medir consumo y costo por chat."""

    __tablename__ = "uso_ia"

    id = Column(Integer, primary_key=True)
    telefono = Column(String, index=True, nullable=False)
    modelo = Column(String, nullable=False)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    costo_usd = Column(Float, default=0.0, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)


BaseSesiones.metadata.create_all(engine_sesiones)


def _migrar_columnas_faltantes():
    """
    create_all() no agrega columnas nuevas a una tabla que ya existe.
    Si sesiones.db viene de una versión anterior del modelo, esto agrega
    cualquier columna que falte sin tocar los datos existentes.
    """
    columnas_existentes = {
        col["name"] for col in inspect(engine_sesiones).get_columns("sesiones")
    }
    faltantes = [c for c in Sesion.__table__.columns if c.name not in columnas_existentes]
    if not faltantes:
        return
    with engine_sesiones.begin() as conexion:
        for columna in faltantes:
            tipo_sql = columna.type.compile(engine_sesiones.dialect)
            conexion.execute(text(f"ALTER TABLE sesiones ADD COLUMN {columna.name} {tipo_sql}"))


_migrar_columnas_faltantes()


def obtener_o_crear_sesion(telefono: str) -> Sesion:
    db = SessionSesiones()
    try:
        sesion = db.query(Sesion).filter(Sesion.telefono == telefono).first()

        if sesion is None:
            sesion = Sesion(telefono=telefono, estado="esperando_codigo")
            db.add(sesion)
            db.commit()
            db.refresh(sesion)

        db.expunge(sesion)
        return sesion
    finally:
        db.close()


def obtener_sesion_existente(telefono: str) -> Sesion | None:
    """
    Busca una sesión sin crearla si no existe. Devuelve None si el
    teléfono no tiene ninguna conversación registrada.
    """
    db = SessionSesiones()
    try:
        sesion = db.query(Sesion).filter(Sesion.telefono == telefono).first()
        if sesion:
            db.expunge(sesion)
        return sesion
    finally:
        db.close()


def actualizar_sesion(telefono: str, **cambios) -> bool:
    """
    Actualiza los campos dados de una sesión existente. Devuelve
    True si encontró la sesión y la actualizó, False si el teléfono
    no tiene ninguna sesión registrada.
    """
    db = SessionSesiones()
    try:
        sesion = db.query(Sesion).filter(Sesion.telefono == telefono).first()
        if sesion:
            for campo, valor in cambios.items():
                if not hasattr(sesion, campo):
                    raise ValueError(f"Campo de sesión desconocido: {campo}")
                setattr(sesion, campo, valor)
            # Leer una conversación no es actividad nueva del cliente. Si
            # actualizáramos actualizado_en aquí, el siguiente polling la
            # marcaría inmediatamente como no leída otra vez.
            if set(cambios) != {"ultimo_leido_panel"}:
                sesion.actualizado_en = datetime.utcnow()
            campos_operativos = {
                "aviso_retiro_pendiente", "solicitud_domicilio_pendiente",
                "pago_reportado", "pago_confirmado", "paquetes_preparados",
                "domicilio_coordinado", "entregado",
            }
            if campos_operativos.intersection(cambios):
                sesion.solicitud_actualizada_en = datetime.utcnow()
            db.commit()
            return True
        return False
    finally:
        db.close()


def listar_sesiones_escaladas() -> list[Sesion]:
    """
    Devuelve todas las sesiones que actualmente tienen
    necesita_atencion_humana=True (casos escalados sin resolver).
    """
    db = SessionSesiones()
    try:
        sesiones = db.query(Sesion).filter(Sesion.necesita_atencion_humana == True).all()  # noqa: E712
        for sesion in sesiones:
            db.expunge(sesion)
        return sesiones
    finally:
        db.close()


def listar_sesiones_con_retiro_pendiente() -> list[Sesion]:
    """
    Devuelve todas las sesiones que actualmente tienen
    aviso_retiro_pendiente=True (retiros avisados sin entregar todavía).
    """
    db = SessionSesiones()
    try:
        sesiones = db.query(Sesion).filter(Sesion.aviso_retiro_pendiente == True).all()  # noqa: E712
        for sesion in sesiones:
            db.expunge(sesion)
        return sesiones
    finally:
        db.close()


def listar_sesiones_con_domicilio_pendiente() -> list[Sesion]:
    """
    Devuelve todas las sesiones que actualmente tienen
    solicitud_domicilio_pendiente=True (entregas a domicilio
    solicitadas sin completar todavía).
    """
    db = SessionSesiones()
    try:
        sesiones = db.query(Sesion).filter(Sesion.solicitud_domicilio_pendiente == True).all()  # noqa: E712
        for sesion in sesiones:
            db.expunge(sesion)
        return sesiones
    finally:
        db.close()


def listar_todas_sesiones(limite: int = 50) -> list[Sesion]:
    """
    Devuelve las sesiones más recientemente actualizadas, sin filtrar
    por estado. Se usa para el panel de administración (vista general
    de conversaciones). Ordenadas por actualizado_en descendente y
    limitadas a `limite` para no devolver toda la tabla de una vez.
    """
    db = SessionSesiones()
    try:
        sesiones = (
            db.query(Sesion)
            .order_by(Sesion.actualizado_en.desc())
            .limit(limite)
            .all()
        )
        for sesion in sesiones:
            db.expunge(sesion)
        return sesiones
    finally:
        db.close()


def listar_sesiones_con_factura_pendiente() -> list[Sesion]:
    """
    Devuelve las sesiones con una factura pendiente de confirmación de
    pago guardada (factura_pendiente_notificacion no vacío).
    """
    db = SessionSesiones()
    try:
        sesiones = (
            db.query(Sesion)
            .filter(Sesion.factura_pendiente_notificacion.isnot(None))
            .all()
        )
        for sesion in sesiones:
            db.expunge(sesion)
        return sesiones
    finally:
        db.close()


def agregar_al_historial(
    telefono: str,
    rol: str,
    contenido: str,
    max_mensajes: int = 100,
    *,
    tipo: str | None = None,
    media_id: str | None = None,
    mime_type: str | None = None,
    whatsapp_message_id: str | None = None,
    estado_entrega: str | None = None,
):
    """
    Agrega un mensaje al historial de la conversación, y recorta
    el historial si supera max_mensajes (para no mandar contexto
    infinito a Claude, lo cual encarecería cada llamada).
    """
    db = SessionSesiones()
    try:
        sesion = db.query(Sesion).filter(Sesion.telefono == telefono).first()
        if sesion is None:
            return

        historial = json.loads(sesion.historial_json or "[]")
        mensaje = {
            "role": rol,
            "content": contenido,
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
        }
        metadatos = {
            "tipo": tipo,
            "media_id": media_id,
            "mime_type": mime_type,
            "whatsapp_message_id": whatsapp_message_id,
            "estado_entrega": estado_entrega,
        }
        mensaje.update({clave: valor for clave, valor in metadatos.items() if valor})
        historial.append(mensaje)
        historial = historial[-max_mensajes:]

        sesion.historial_json = json.dumps(historial)
        sesion.actualizado_en = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def actualizar_estado_mensaje_whatsapp(
    whatsapp_message_id: str,
    estado: str,
    error_entrega: str | None = None,
) -> bool:
    """Actualiza el recibo de entrega sin convertir el chat en no leído."""
    if not whatsapp_message_id:
        return False
    db = SessionSesiones()
    try:
        sesiones = (
            db.query(Sesion)
            .filter(Sesion.historial_json.contains(whatsapp_message_id))
            .all()
        )
        for sesion in sesiones:
            historial = json.loads(sesion.historial_json or "[]")
            actualizado = False
            for mensaje in historial:
                if mensaje.get("whatsapp_message_id") == whatsapp_message_id:
                    mensaje["estado_entrega"] = estado
                    if error_entrega:
                        mensaje["error_entrega"] = error_entrega[:300]
                    actualizado = True
            if actualizado:
                sesion.historial_json = json.dumps(historial)
                db.commit()
                return True
        return False
    finally:
        db.close()


def registrar_uso_ia(
    telefono: str,
    modelo: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Guarda el consumo de una llamada y devuelve su costo estimado."""
    costo = round(
        (input_tokens / 1_000_000) * settings.ANTHROPIC_INPUT_USD_PER_MTOK
        + (output_tokens / 1_000_000) * settings.ANTHROPIC_OUTPUT_USD_PER_MTOK,
        8,
    )
    db = SessionSesiones()
    try:
        db.add(UsoIA(
            telefono=telefono,
            modelo=modelo,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            costo_usd=costo,
        ))
        db.commit()
        return costo
    finally:
        db.close()


def obtener_uso_por_telefono(telefono: str) -> dict:
    db = SessionSesiones()
    try:
        filas = db.query(UsoIA).filter(UsoIA.telefono == telefono).all()
        return {
            "input_tokens": sum(f.input_tokens for f in filas),
            "output_tokens": sum(f.output_tokens for f in filas),
            "costo_usd": round(sum(f.costo_usd for f in filas), 6),
            "llamadas": len(filas),
        }
    finally:
        db.close()


def obtener_resumen_uso(dias: int = 30) -> dict:
    desde = datetime.utcnow() - timedelta(days=max(1, min(dias, 365)))
    db = SessionSesiones()
    try:
        filas = db.query(UsoIA).filter(UsoIA.creado_en >= desde).all()
        por_dia = {}
        por_chat = {}
        for fila in filas:
            dia = fila.creado_en.date().isoformat()
            diario = por_dia.setdefault(dia, {"input_tokens": 0, "output_tokens": 0, "costo_usd": 0.0})
            diario["input_tokens"] += fila.input_tokens
            diario["output_tokens"] += fila.output_tokens
            diario["costo_usd"] += fila.costo_usd
            chat = por_chat.setdefault(fila.telefono, {"input_tokens": 0, "output_tokens": 0, "costo_usd": 0.0, "llamadas": 0})
            chat["input_tokens"] += fila.input_tokens
            chat["output_tokens"] += fila.output_tokens
            chat["costo_usd"] += fila.costo_usd
            chat["llamadas"] += 1

        total_input = sum(f.input_tokens for f in filas)
        total_output = sum(f.output_tokens for f in filas)
        total_costo = sum(f.costo_usd for f in filas)
        return {
            "dias": [
                {"fecha": fecha, **valores, "costo_usd": round(valores["costo_usd"], 6)}
                for fecha, valores in sorted(por_dia.items())
            ],
            "chats": [
                {"telefono": telefono, **valores, "costo_usd": round(valores["costo_usd"], 6)}
                for telefono, valores in sorted(
                    por_chat.items(), key=lambda item: item[1]["costo_usd"], reverse=True
                )
            ],
            "input_tokens": total_input,
            "output_tokens": total_output,
            "tokens_totales": total_input + total_output,
            "costo_usd": round(total_costo, 6),
            "conversaciones": len(por_chat),
        }
    finally:
        db.close()
