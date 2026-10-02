"""Papelera compartida de avisos; no modifica los casos que los originan."""

import hashlib

from sqlalchemy.exc import IntegrityError

from app.db.session_store import AlertaArchivada, SessionSesiones


def _serializar(fila):
    return {
        "id": fila.id, "clave": fila.clave, "titulo": fila.titulo,
        "descripcion": fila.descripcion, "motivo": fila.motivo,
        "usuario": fila.usuario, "creado_en": fila.creado_en.isoformat() + "Z",
    }


def listar_archivadas():
    with SessionSesiones() as db:
        return [_serializar(f) for f in db.query(AlertaArchivada).order_by(AlertaArchivada.id.desc()).all()]


def archivar_alerta(clave, titulo, descripcion, motivo, usuario):
    firma = hashlib.sha256(clave.encode("utf-8")).hexdigest()
    with SessionSesiones() as db:
        fila = db.query(AlertaArchivada).filter_by(firma=firma).first()
        if fila:
            return _serializar(fila)
        fila = AlertaArchivada(firma=firma, clave=clave, titulo=titulo,
                              descripcion=descripcion, motivo=motivo, usuario=usuario)
        db.add(fila)
        try:
            db.commit()
        except IntegrityError:
            # Dos operadores pueden quitar el mismo aviso a la vez.
            db.rollback()
            fila = db.query(AlertaArchivada).filter_by(firma=firma).one()
        db.refresh(fila)
        return _serializar(fila)


def restaurar_alerta(alerta_id):
    with SessionSesiones() as db:
        fila = db.get(AlertaArchivada, alerta_id)
        if fila is None:
            return False
        db.delete(fila)
        db.commit()
        return True
