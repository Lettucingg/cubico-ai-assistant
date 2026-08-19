import json

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

engine_sesiones = create_engine("sqlite:///sesiones.db")
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
    actualizado_en = Column(DateTime, default=datetime.utcnow)

    def obtener_historial(self):
        """Convierte el historial guardado (texto JSON) en una lista de Python."""
        return json.loads(self.historial_json or "[]")


BaseSesiones.metadata.create_all(engine_sesiones)


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


def actualizar_sesion(telefono: str, **cambios):
    db = SessionSesiones()
    try:
        sesion = db.query(Sesion).filter(Sesion.telefono == telefono).first()
        if sesion:
            for campo, valor in cambios.items():
                setattr(sesion, campo, valor)
            sesion.actualizado_en = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def agregar_al_historial(telefono: str, rol: str, contenido: str, max_mensajes: int = 8):
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
        historial.append({"role": rol, "content": contenido})
        historial = historial[-max_mensajes:]

        sesion.historial_json = json.dumps(historial)
        sesion.actualizado_en = datetime.utcnow()
        db.commit()
    finally:
        db.close()
