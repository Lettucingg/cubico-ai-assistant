from app.db.database import SessionLocal
from app.db.models import ClienteCBC


def verificar_cliente(codigo: str, email: str) -> bool:
    """
    Verifica que el código de cliente y el correo coincidan con un
    registro real en la base de datos de Cúbico.

    Comparamos el correo sin distinguir mayúsculas/minúsculas ni
    espacios extra al inicio/final, ya que los clientes pueden
    escribirlo de formas ligeramente distintas.
    """
    db = SessionLocal()
    try:
        cliente = (
            db.query(ClienteCBC)
            .filter(ClienteCBC.codigo == codigo.strip().upper())
            .first()
        )

        if cliente is None or cliente.email is None:
            return False

        return cliente.email.strip().lower() == email.strip().lower()

    finally:
        db.close()


def obtener_nombre_completo_cliente(codigo_cliente: str) -> dict:
    """
    Busca un cliente por su código CBC y devuelve su nombre completo.
    Se usa para personalizar mensajes (ej: la dirección de Miami) una
    vez que el cliente ya fue verificado.
    """
    db = SessionLocal()
    try:
        cliente = (
            db.query(ClienteCBC)
            .filter(ClienteCBC.codigo == codigo_cliente.strip().upper())
            .first()
        )

        if cliente is None:
            return {
                "encontrado": False,
                "mensaje": f"No se encontró ningún cliente con el código {codigo_cliente}.",
            }

        return {
            "encontrado": True,
            "nombre_completo": f"{cliente.nombre} {cliente.apellido or ''}".strip(),
        }
    finally:
        db.close()