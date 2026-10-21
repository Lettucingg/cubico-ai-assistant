"""Team incident tracker. Content is never injected into Bruno's instructions."""
import json
from datetime import datetime
from sqlalchemy import select
from app.db.session_store import IncidenciaPanel, SessionSesiones
from app.services.panel_profile import validate_photo

SECTIONS = {'overview', 'chats', 'packages', 'opportunities', 'costs', 'alerts', 'operations', 'settings', 'incidents', 'general'}
STATES = {'pendiente', 'en_revision', 'resuelta', 'descartada'}


def serialize(row, detail=False):
    data = json.loads(row.contenido)
    data.update(id=row.id, codigo=f'INC-{row.id:04d}', creado_en=row.creado_en.isoformat()+'Z', actualizado_en=row.actualizado_en.isoformat()+'Z')
    if not detail:
        data.pop('captura', None)
        data.pop('historial', None)
    return data


def listing(status=None, section=None, limit=200):
    # A bounded page; filters happen before the limit so resolved records cannot hide open work.
    with SessionSesiones() as db:
        rows = db.scalars(select(IncidenciaPanel).order_by(IncidenciaPanel.actualizado_en.desc(), IncidenciaPanel.id.desc()))
        result = []
        for row in rows:
            data = serialize(row)
            if status and data['estado'] != status or section and data['seccion'] != section:
                continue
            result.append(data)
            if len(result) >= limit:
                break
        return result


def get(incident_id):
    with SessionSesiones() as db:
        row = db.get(IncidenciaPanel, incident_id)
        if row is None:
            raise LookupError('No existe esta incidencia.')
        return serialize(row, True)


def create(data, actor):
    if data['seccion'] not in SECTIONS or data['tipo'] not in {'problema', 'mejora'} or data['prioridad'] not in {'baja', 'normal', 'alta'}:
        raise ValueError('Revisa la sección, el tipo y la prioridad.')
    if not data['titulo'].strip() or not data['descripcion'].strip():
        raise ValueError('Escribe un título y describe lo que ocurrió.')
    validate_photo(data.get('captura'))
    now = datetime.utcnow()
    content = {**data, 'titulo': data['titulo'].strip(), 'descripcion': data['descripcion'].strip(), 'creador': actor, 'responsable': None, 'estado': 'pendiente', 'revision': 1,
               'historial': [{'usuario': actor, 'fecha': now.isoformat()+'Z', 'accion': 'Creada'}]}
    with SessionSesiones() as db:
        row = IncidenciaPanel(contenido=json.dumps(content, ensure_ascii=False), creado_en=now, actualizado_en=now)
        db.add(row); db.commit(); db.refresh(row)
        return serialize(row, True)


def update(incident_id, data, actor, users):
    if data['estado'] not in STATES or data['prioridad'] not in {'baja', 'normal', 'alta'}:
        raise ValueError('Estado o prioridad no válidos.')
    if data['responsable'] and data['responsable'] not in users:
        raise ValueError('El responsable debe tener acceso al panel.')
    with SessionSesiones() as db:
        row = db.get(IncidenciaPanel, incident_id)
        if row is None:
            raise LookupError('No existe esta incidencia.')
        current = json.loads(row.contenido)
        if current['revision'] != data['revision']:
            raise RuntimeError('Otra persona actualizó esta incidencia. Ábrela de nuevo para ver los cambios.')
        now = datetime.utcnow()
        actions = []
        for key in ('estado', 'prioridad', 'responsable'):
            if current[key] != data[key]:
                actions.append(f'{key}: {current[key] or "sin asignar"} → {data[key] or "sin asignar"}')
                current[key] = data[key]
        note = data.get('nota', '').strip()
        if not actions and not note:
            return serialize(row, True)
        if len(current['historial']) >= 500:
            raise ValueError('Se alcanzó el límite de seguimiento de esta incidencia.')
        current['historial'].append({'usuario': actor, 'fecha': now.isoformat()+'Z', 'accion': '; '.join(actions), 'nota': note})
        current['revision'] += 1
        # Compare-and-swap prevents simultaneous editors from losing another person's notes.
        old_content = row.contenido
        from sqlalchemy import update as sql_update
        changed = db.execute(sql_update(IncidenciaPanel).where(IncidenciaPanel.id == incident_id, IncidenciaPanel.contenido == old_content).values(contenido=json.dumps(current, ensure_ascii=False), actualizado_en=now)).rowcount
        if changed != 1:
            db.rollback()
            raise RuntimeError('Otra persona actualizó esta incidencia. Ábrela de nuevo.')
        db.commit(); db.expire_all()
        return serialize(db.get(IncidenciaPanel, incident_id), True)
