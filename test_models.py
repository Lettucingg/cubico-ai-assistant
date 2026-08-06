"""
Script de prueba TEMPORAL. No es parte del proyecto final.
Sirve para confirmar que los modelos de SQLAlchemy (app/db/models.py)
funcionan correctamente, sin necesitar la base de datos real de Cúbico.

Usa SQLite en memoria: una base de datos que vive solo mientras
corre este script y desaparece al terminar. Perfecta para pruebas
rápidas y aisladas.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import ClienteCBC, Paquete

# Motor de prueba: SQLite en memoria (no crea ningún archivo en disco)
engine_prueba = create_engine("sqlite:///:memory:")

# Crea todas las tablas definidas en models.py dentro de esta base temporal
Base.metadata.create_all(engine_prueba)

SessionPrueba = sessionmaker(bind=engine_prueba)
db = SessionPrueba()

# 1. Crear un cliente de prueba
cliente_prueba = ClienteCBC(
    codigo="CBC-0001",
    nombre="Juan",
    apellido="Pérez",
    email="juan@correo.com",
    telefono="+50760000000",
)
db.add(cliente_prueba)
db.commit()

# 2. Crear un paquete asociado a ese cliente
paquete_prueba = Paquete(
    tracking="TRK-12345",
    nombre_destinatario="Juan Pérez",
    peso=5.5,
    estado_cargo="en_miami",
    estado_pago="pendiente",
    tipo_cliente="cbc",
    cliente_cbc_id=cliente_prueba.id,
)
db.add(paquete_prueba)
db.commit()

# 3. Consultar: ¿la relación cliente -> paquetes funciona?
cliente_consultado = db.query(ClienteCBC).filter(ClienteCBC.codigo == "CBC-0001").first()

print("Cliente encontrado:", cliente_consultado.nombre, cliente_consultado.apellido)
print("Cantidad de paquetes:", len(cliente_consultado.paquetes))
print("Tracking del primer paquete:", cliente_consultado.paquetes[0].tracking)
print("Estado del paquete:", cliente_consultado.paquetes[0].estado_cargo)

db.close()
print("\nPrueba completada sin errores. Los modelos funcionan correctamente.")