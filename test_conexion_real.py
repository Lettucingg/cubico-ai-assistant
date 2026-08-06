"""
Script de prueba TEMPORAL. Verifica que la conexión real a la base
de datos de PostgreSQL de Cúbico funciona correctamente.

Hace una sola consulta de SOLO LECTURA (contar clientes), no modifica
absolutamente nada en la base de datos real.
"""

from sqlalchemy import text
from app.db.database import engine

print("Intentando conectar a la base de datos real de Cúbico...\n")

try:
    with engine.connect() as conn:
        resultado = conn.execute(text("SELECT COUNT(*) FROM clientes_cbc"))
        cantidad = resultado.scalar()
        print(f"✅ Conexión exitosa.")
        print(f"Cantidad de clientes registrados en clientes_cbc: {cantidad}")

except Exception as e:
    print("❌ Error al conectar con la base de datos.")
    print(f"Detalle del error: {e}")
    