from app.db.session_store import PreferenciasAvisos, SessionSesiones


def obtener(usuario):
    with SessionSesiones() as db:
        row = db.get(PreferenciasAvisos, usuario)
        return row.categoria if row else "ambos"


def guardar(usuario, categoria):
    if categoria not in {"ambos", "alertas", "chats"}:
        raise ValueError("Categoría inválida")
    with SessionSesiones() as db:
        row = db.get(PreferenciasAvisos, usuario)
        if row is None:
            row = PreferenciasAvisos(usuario=usuario)
            db.add(row)
        row.categoria = categoria
        db.commit()
    return categoria


def permite(usuario, categoria):
    preferencia = obtener(usuario)
    return preferencia == "ambos" or preferencia == categoria
