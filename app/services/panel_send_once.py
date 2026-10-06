import hashlib
import inspect
import json
from functools import wraps
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from app.db.session_store import EnvioPanelUnico, SessionSesiones


def envio_unico(func):
    signature = inspect.signature(func)

    @wraps(func)
    async def wrapped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs).arguments
        body = bound['body']
        request_id = body.get('request_id')
        if not request_id:
            return await func(*args, **kwargs)  # Compatibilidad con clientes anteriores.
        if not isinstance(request_id, str) or len(request_id) > 128:
            raise HTTPException(status_code=422, detail='Identificador de envío inválido')
        key = hashlib.sha256(f"{func.__name__}:{bound['usuario']}:{bound['telefono']}:{request_id}".encode()).hexdigest()
        mensaje = body.get('mensaje', '')
        if not isinstance(mensaje, str):
            raise HTTPException(status_code=422, detail='Mensaje inválido')
        content = hashlib.sha256(mensaje.encode()).hexdigest()
        with SessionSesiones() as db:
            row = EnvioPanelUnico(clave=key, contenido_hash=content)
            db.add(row)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                row = db.get(EnvioPanelUnico, key)
                if row.contenido_hash != content:
                    raise HTTPException(status_code=409, detail='Este envío corresponde a otro texto')
                if row.resultado:
                    return json.loads(row.resultado)
                raise HTTPException(status_code=409, detail='El envío ya se está procesando o no se pudo confirmar. Revisa el historial antes de enviar otra vez.')
        # Ante un resultado incierto conservamos la reserva, sin repetir WhatsApp.
        result = await func(*args, **kwargs)
        with SessionSesiones() as db:
            db.get(EnvioPanelUnico, key).resultado = json.dumps(result)
            db.commit()
        return result
    return wrapped
