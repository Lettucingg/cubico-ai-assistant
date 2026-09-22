import re

from sqlalchemy import func

from app.db.database import SessionLocal
from app.db.models import Agencia, ClienteCBC


def normalizar_codigo_cbc(codigo: str) -> str:
    """Devuelve el formato canónico CBC-XXXX sin alterar el sufijo real."""
    compacto = re.sub(r"[\s_-]+", "", (codigo or "").strip().upper())
    if compacto.startswith("CBC") and len(compacto) > 3:
        return f"CBC-{compacto[3:]}"
    return (codigo or "").strip().upper()


def normalizar_codigo_cliente(codigo: str) -> str:
    """Normaliza códigos personales CBC y códigos propios de agencias."""
    codigo_limpio = (codigo or "").strip().upper()
    if re.sub(r"[\s_-]+", "", codigo_limpio).startswith("CBC"):
        return normalizar_codigo_cbc(codigo_limpio)
    return re.sub(r"\s+", "", codigo_limpio)


def variantes_codigo_cbc(codigo: str) -> set[str]:
    """Acepta el código con o sin guion al consultar registros existentes."""
    canonico = normalizar_codigo_cbc(codigo)
    compacto = canonico.replace("-", "")
    return {valor for valor in (canonico, compacto) if valor}


def filtro_cliente_activo_por_codigo(codigo: str):
    """Condiciones SQL reutilizables para un cliente activo por código CBC."""
    return (
        func.upper(ClienteCBC.codigo).in_(variantes_codigo_cbc(codigo)),
        ClienteCBC.activo.isnot(False),
    )


def buscar_identidad_activa_por_codigo(db, codigo: str):
    """Devuelve tipo, registro y código canónico para persona o agencia."""
    codigo_normalizado = normalizar_codigo_cliente(codigo)
    if not codigo_normalizado:
        return None, None, codigo_normalizado

    cliente = (
        db.query(ClienteCBC)
        .filter(*filtro_cliente_activo_por_codigo(codigo_normalizado))
        .first()
    )
    if cliente is not None:
        return "cbc", cliente, normalizar_codigo_cbc(cliente.codigo)

    agencia = (
        db.query(Agencia)
        .filter(
            func.upper(Agencia.codigo) == codigo_normalizado,
            Agencia.activo.isnot(False),
        )
        .first()
    )
    if agencia is not None:
        return "agencia", agencia, str(agencia.codigo).strip().upper()

    return None, None, codigo_normalizado


def verificar_identidad_cliente(codigo: str, email: str) -> dict:
    """Verifica por código y correo tanto clientes personales como agencias."""
    db = SessionLocal()
    try:
        tipo, registro, codigo_normalizado = buscar_identidad_activa_por_codigo(
            db, codigo
        )
        email_normalizado = (email or "").strip().lower()
        coincide = bool(
            registro is not None
            and registro.email
            and registro.email.strip().lower() == email_normalizado
        )
        if not coincide:
            return {"verificado": False}
        nombre = (
            f"{registro.nombre} {getattr(registro, 'apellido', '') or ''}".strip()
            if tipo == "cbc"
            else str(registro.nombre).strip()
        )
        return {
            "verificado": True,
            "codigo_cliente": codigo_normalizado,
            "tipo_cliente": tipo,
            "nombre_completo": nombre,
        }
    finally:
        db.close()


def verificar_cliente(codigo: str, email: str) -> bool:
    """
    Compatibilidad: verifica que el código y correo coincidan con una
    persona o agencia real en la base de datos de Cúbico.

    Comparamos el correo sin distinguir mayúsculas/minúsculas ni
    espacios extra al inicio/final, ya que los clientes pueden
    escribirlo de formas ligeramente distintas.
    """
    return bool(verificar_identidad_cliente(codigo, email).get("verificado"))


def verificar_correo_registrado(email: str) -> dict:
    """
    Busca si existe alguna persona o agencia registrada con ese correo,
    sin necesitar su código. Se usa para problemas de acceso/login
    en la web, donde el cliente todavía no tiene su código a mano.

    Comparamos el correo sin distinguir mayúsculas/minúsculas ni
    espacios extra, igual que en verificar_cliente. Escapamos los
    comodines de LIKE (% y _) para que la búsqueda sea siempre una
    coincidencia exacta del correo, no un patrón.
    """
    email_escapado = (
        email.strip()
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )

    db = SessionLocal()
    try:
        cliente = (
            db.query(ClienteCBC)
            .filter(ClienteCBC.email.isnot(None))
            .filter(ClienteCBC.activo.isnot(False))
            .filter(ClienteCBC.email.ilike(email_escapado, escape="\\"))
            .first()
        )
        agencia = (
            db.query(Agencia)
            .filter(Agencia.email.isnot(None))
            .filter(Agencia.activo.isnot(False))
            .filter(Agencia.email.ilike(email_escapado, escape="\\"))
            .first()
        )

        return {"registrado": cliente is not None or agencia is not None}

    finally:
        db.close()


def obtener_nombre_completo_cliente(codigo_cliente: str) -> dict:
    """
    Busca una persona o agencia por su código y devuelve su nombre.
    Se usa para personalizar mensajes (ej: la dirección de Miami) una
    vez que el cliente ya fue verificado.
    """
    db = SessionLocal()
    try:
        tipo, registro, codigo_normalizado = buscar_identidad_activa_por_codigo(
            db, codigo_cliente
        )

        if registro is None:
            return {
                "encontrado": False,
                "mensaje": f"No se encontró ningún cliente con el código {codigo_cliente}.",
            }

        nombre = (
            f"{registro.nombre} {getattr(registro, 'apellido', '') or ''}".strip()
            if tipo == "cbc"
            else str(registro.nombre).strip()
        )
        return {
            "encontrado": True,
            "nombre_completo": nombre,
            "tipo_cliente": tipo,
            "codigo_cliente": codigo_normalizado,
        }
    finally:
        db.close()
