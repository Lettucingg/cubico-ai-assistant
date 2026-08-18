from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

# Esta es una base de datos PROPIA del bot, separada por completo de
# la base de datos de Cúbico (que es de solo lectura). Aquí guardamos
# información que solo le importa al bot: en qué paso de verificación
# está cada número de teléfono.
engine_sesiones = create_engine("sqlite:///sesiones.db")
SessionSesiones = sessionmaker(bind=engine_sesiones)
BaseSesiones = declarative_base()


class Sesion(BaseSesiones):
    """
    Representa el estado de la conversación con un número de
    teléfono específico.

    estado puede ser:
      - "esperando_codigo": recién empezó, pedimos el código CBC
      - "esperando_correo": ya dio el código, pedimos el correo
      - "verificado": ya se identificó correctamente
    """
    __tablename__ = "sesiones"

    id = Column(Integer, primary_key=True)
    telefono = Column(String, unique=True, nullable=False)
    estado = Column(String, default="esperando_codigo")
    codigo_cliente_temporal = Column(String, nullable=True)
    codigo_cliente_verificado = Column(String, nullable=True)
    actualizado_en = Column(DateTime, default=datetime.utcnow)


BaseSesiones.metadata.create_all(engine_sesiones)


def obtener_o_crear_sesion(telefono: str) -> Sesion:
    """
    Busca la sesión de un teléfono. Si no existe, crea una nueva
    en estado "esperando_codigo".
    """
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
    """
    Actualiza campos específicos de la sesión de un teléfono.
    """
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