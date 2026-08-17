from app.db.database import SessionLocal
from app.db.models import ClienteCBC


def consultar_paquetes_por_codigo(codigo_cliente: str) -> dict:
    """
    Busca un cliente por su código CBC (ej: "CBC-0001") y devuelve
    la lista de sus paquetes.

    Esta función es una "herramienta" que Claude va a poder invocar
    cuando un cliente pregunte por sus paquetes. Claude NUNCA inventa
    esta información — siempre pasa por aquí, que consulta la base
    de datos real de Cúbico.

    Devuelve un diccionario simple (no objetos de SQLAlchemy), listo
    para convertirse en JSON y mandarse de vuelta a Claude.
    """
    db = SessionLocal()
    try:
        cliente = (
            db.query(ClienteCBC)
            .filter(ClienteCBC.codigo == codigo_cliente)
            .first()
        )

        if cliente is None:
            return {
                "encontrado": False,
                "mensaje": f"No se encontró ningún cliente con el código {codigo_cliente}.",
            }

        paquetes = []
        for paquete in cliente.paquetes:
            paquetes.append({
                "tracking": paquete.tracking,
                "estado_cargo": paquete.estado_cargo,
                "estado_pago": paquete.estado_pago,
                "peso": float(paquete.peso) if paquete.peso else None,
                "costo": float(paquete.costo) if paquete.costo else None,
            })

        return {
            "encontrado": True,
            "cliente": f"{cliente.nombre} {cliente.apellido or ''}".strip(),
            "cantidad_paquetes": len(paquetes),
            "paquetes": paquetes,
        }

    finally:
        db.close()