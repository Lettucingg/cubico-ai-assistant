"""Revocable per-operator MCP credentials. Only token digests are persisted."""
import hashlib
import json
import secrets
from datetime import datetime, timedelta
from sqlalchemy import select, update
from app.db.session_store import ConexionIAPanel, SessionSesiones

SCOPES = {'conversaciones', 'cuentas', 'incidencias', 'operacion'}


def summary(row):
    return {'id': row.id, 'nombre': row.nombre, 'permisos': json.loads(row.permisos),
            'creado_en': row.creado_en.isoformat()+'Z', 'vence_en': row.vence_en.isoformat()+'Z',
            'revocado': row.revocado, 'vencido': row.vence_en <= datetime.utcnow(),
            'ultimo_uso': row.ultimo_uso.isoformat()+'Z' if row.ultimo_uso else None,
            'ultima_herramienta': row.ultima_herramienta}


def listing(user):
    with SessionSesiones() as db:
        rows = db.scalars(select(ConexionIAPanel).where(ConexionIAPanel.usuario == user).order_by(ConexionIAPanel.creado_en.desc()).limit(100))
        return [summary(r) for r in rows]


def issue(user, name, scopes):
    if not name.strip() or not scopes or not set(scopes) <= SCOPES:
        raise ValueError('Elige un nombre y al menos un permiso válido.')
    if 'cuentas' in scopes and 'conversaciones' not in scopes:
        raise ValueError('Para consultar cuentas también debes habilitar conversaciones.')
    now = datetime.utcnow()
    token = 'cubico_' + secrets.token_urlsafe(32)
    with SessionSesiones() as db:
        active = list(db.scalars(select(ConexionIAPanel).where(ConexionIAPanel.usuario == user, ConexionIAPanel.revocado.is_(False), ConexionIAPanel.vence_en > now)))
        if len(active) >= 10:
            raise ValueError('Revoca una conexión antes de crear otra. Máximo: 10 activas.')
        row = ConexionIAPanel(id=secrets.token_hex(16), usuario=user, nombre=name.strip(), token_hash=hashlib.sha256(token.encode()).hexdigest(), permisos=json.dumps(sorted(set(scopes))), creado_en=now, vence_en=now+timedelta(days=90))
        db.add(row); db.commit(); db.refresh(row)
        return {**summary(row), 'token': token}


def revoke(user, connection_id):
    with SessionSesiones() as db:
        row = db.get(ConexionIAPanel, connection_id)
        if row is None or row.usuario != user:
            raise LookupError('No existe esta conexión en tu cuenta.')
        row.revocado = True
        db.commit()


def authenticate(token, users):
    if not token or len(token) > 200:
        return None
    with SessionSesiones() as db:
        row = db.scalar(select(ConexionIAPanel).where(ConexionIAPanel.token_hash == hashlib.sha256(token.encode()).hexdigest()))
        if row and not row.revocado and row.vence_en > datetime.utcnow() and row.usuario in users:
            return {'id': row.id, 'usuario': row.usuario, 'permisos': json.loads(row.permisos)}
    from app.services.staff_oauth import actor_for_token
    actor = actor_for_token(token)
    return actor if actor and actor['usuario'] in users else None


def touch(identity, tool=None):
    """Atomic per-credential rate limit across workers; no conversation content in audit."""
    now = datetime.utcnow(); minute = int(now.timestamp() // 60)
    with SessionSesiones() as db:
        base = (ConexionIAPanel.id == identity['id'], ConexionIAPanel.revocado.is_(False), ConexionIAPanel.vence_en > now)
        db.execute(update(ConexionIAPanel).where(*base, ConexionIAPanel.minuto != minute).values(minuto=minute, peticiones=0))
        values = {'peticiones': ConexionIAPanel.peticiones+1, 'ultimo_uso': now}
        if tool:
            values['ultima_herramienta'] = tool
        changed = db.execute(update(ConexionIAPanel).where(*base, ConexionIAPanel.peticiones < 60).values(**values)).rowcount
        db.commit()
        return changed == 1
