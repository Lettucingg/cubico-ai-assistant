"""Bounded, paused-by-default pilot. Each recipient is attempted at most once."""
import argparse
import asyncio
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.exc import IntegrityError
from app.db.session_store import BaseSesiones, SessionSesiones, engine_sesiones, obtener_sesion_existente
from app.services import outbound_templates as templates
from app.services.marketing_preferences import is_suppressed

PROMOTION = 'cubico_tarifa_preferencial_210'
LANGUAGE = 'es_PA'
CAMPAIGN = 'SOMOSCUBICO_WA_LOTE1'


class PilotBatch(BaseSesiones):
    __tablename__ = 'campaign_pilot_batches'
    id = Column(String(64), primary_key=True)
    estado = Column(String(30), nullable=False, default='pausada')
    plantilla_json = Column(Text, nullable=False)
    fuente_hash = Column(String(64), nullable=False)
    operador = Column(String(100), nullable=False)
    creada_en = Column(DateTime, nullable=False, default=datetime.utcnow)
    desde = Column(DateTime, nullable=True)
    hasta = Column(DateTime, nullable=True)
    siguiente_intento = Column(DateTime, nullable=True)
    detalle = Column(String(500), nullable=True)


class PilotRecipient(BaseSesiones):
    __tablename__ = 'campaign_pilot_recipients'
    __table_args__ = (UniqueConstraint('campana', 'telefono', name='pilot_campaign_phone_unique'),)
    id = Column(Integer, primary_key=True)
    lote = Column(String(64), nullable=False, index=True)
    campana = Column(String(50), nullable=False)
    telefono = Column(String(40), nullable=False)
    nombre = Column(String(300), nullable=False)
    estado = Column(String(30), nullable=False, default='pendiente')
    intento_en = Column(DateTime, nullable=True)
    message_id = Column(String(300), nullable=True)
    detalle = Column(String(500), nullable=True)


for model in (PilotBatch, PilotRecipient):
    model.__table__.create(engine_sesiones, checkfirst=True)


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def read_source(csv_path=None):
    if csv_path:
        with open(csv_path, encoding='utf-8-sig', newline='') as source:
            reader = csv.DictReader(source)
            if not {'nombre', 'telefono', 'campana', 'nota'} <= set(reader.fieldnames or []):
                raise ValueError('El CSV no tiene las columnas de prospectos esperadas')
            return list(reader)
    from app.db.database import engine
    try:
        with engine.connect() as connection:
            return [dict(row) for row in connection.execute(text(
                'SELECT nombre, telefono, campana, nota FROM prospectos_campana ORDER BY id')).mappings()]
    except Exception:
        raise ValueError('No se pudo leer prospectos_campana. Carga la tabla o usa --csv con el archivo privado en el servidor.') from None


def candidates(rows):
    """Never mix email or redirection audiences into this promotion."""
    excluded = Counter()
    redirect = set()
    withdrawn = set()
    for row in rows:
        try:
            number = templates.normalize_phone(str(row.get('telefono') or ''))
        except ValueError:
            continue
        if row.get('campana') == 'S2N_REDIRECCION':
            redirect.add(number)
        if re.search(r'\b(?:SACADO|NO_CONTACTAR|BAJA)\b', str(row.get('nota') or ''), re.I):
            withdrawn.add(number)
    result = []
    seen = set()
    with SessionSesiones() as db:
        reserved = {r.telefono for r in db.query(PilotRecipient).filter_by(campana=CAMPAIGN)}
    for row in rows:
        if row.get('campana') != CAMPAIGN:
            excluded['otra_campana'] += 1
            continue
        try:
            number = templates.normalize_phone(str(row.get('telefono') or ''))
        except ValueError:
            excluded['telefono_invalido'] += 1
            continue
        if number in redirect or number in withdrawn or is_suppressed(number):
            excluded['redireccion_o_baja'] += 1
            continue
        if number in reserved or number in seen:
            excluded['duplicado_o_reservado'] += 1
            continue
        session = obtener_sesion_existente(number)
        if session and (session.atencion_humana_directa or session.necesita_atencion_humana):
            excluded['atencion_en_curso'] += 1
            continue
        name = str(row.get('nombre') or '').strip() or 'cliente'
        if len(name) > 300:
            excluded['nombre_invalido'] += 1
            continue
        seen.add(number)
        result.append({'telefono': number, 'nombre': name})
    return result, dict(excluded)


async def current_template():
    rows = await templates.list_templates()
    found = [r for r in rows if r['nombre'] == PROMOTION and r['idioma'] == LANGUAGE]
    if len(found) != 1 or found[0]['variables'] != 1 or not found[0]['imagen'] or found[0]['categoria'] != 'MARKETING':
        raise ValueError('La promoción esperada no está aprobada o tiene un formato diferente')
    if not (Path(__file__).resolve().parents[1] / 'static' / 'logo.png').is_file():
        raise ValueError('Falta el logo de la promoción')
    return found[0]


async def prepare(key, rows, operator, count=10, permission=False):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', key):
        raise ValueError('Identificador de lote inválido')
    if not 1 <= count <= 10:
        raise ValueError('El piloto admite entre 1 y 10 destinatarios')
    if not permission:
        raise ValueError('Confirma que esta lista tiene permiso para recibir mensajes de WhatsApp; el CSV no lo demuestra por sí solo')
    # Idempotent preparation never silently replaces or expands a reviewed batch.
    with SessionSesiones() as db:
        if db.get(PilotBatch, key):
            return report(key)
    row = await current_template()
    eligible, excluded = candidates(rows)
    selected = eligible[:count]
    if len(selected) < count:
        raise ValueError(f'Solo hay {len(selected)} destinatarios elegibles; solicita una cantidad menor')
    digest = hashlib.sha256(json.dumps(selected, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    try:
        with SessionSesiones() as db:
            db.add(PilotBatch(id=key, plantilla_json=json.dumps(row, ensure_ascii=False), fuente_hash=digest, operador=operator))
            db.add_all([PilotRecipient(lote=key, campana=CAMPAIGN, **recipient) for recipient in selected])
            db.commit()
    except IntegrityError:
        raise ValueError('Otro proceso ya reservó este lote o destinatario; revisa el resumen. No se envió nada.') from None
    return {**report(key), 'elegibles_disponibles': len(eligible), 'exclusiones': excluded,
            'vista_previa': templates.render(row, [selected[0]['nombre']])}


async def activate(key, when):
    if when.tzinfo is None:
        raise ValueError('Indica zona horaria, por ejemplo 2026-11-05T09:00:00-05:00')
    due = when.astimezone(timezone.utc).replace(tzinfo=None)
    if not now_utc() - timedelta(minutes=1) <= due <= now_utc() + timedelta(days=7):
        raise ValueError('La hora debe estar entre ahora y los próximos siete días')
    template = await current_template()
    with SessionSesiones() as db:
        batch = db.get(PilotBatch, key)
        if not batch:
            raise ValueError('No existe ese lote preparado')
        if batch.estado != 'pausada':
            raise ValueError('Solo se activa un lote pausado; revisa su estado')
        if json.loads(batch.plantilla_json)['huella'] != template['huella']:
            raise ValueError('La plantilla cambió. El lote no se activó; requiere nueva revisión')
        batch.estado = 'activa'
        batch.desde = due
        batch.hasta = due + timedelta(hours=1)
        batch.detalle = None
        db.commit()
    return report(key)


def pause(key, reason='Pausada por el equipo'):
    with SessionSesiones() as db:
        batch = db.get(PilotBatch, key)
        if not batch:
            raise ValueError('No existe ese lote')
        batch.estado = 'pausada'
        batch.detalle = reason[:500]
        db.commit()


def report(key):
    from app.services.cost_analytics import CostEvent
    from app.services.delivery_diagnostics import MetaDeliveryReceipt
    with SessionSesiones() as db:
        batch = db.get(PilotBatch, key)
        if not batch:
            raise ValueError('No existe ese lote')
        result = []
        for recipient in db.query(PilotRecipient).filter_by(lote=key).order_by(PilotRecipient.id):
            state = recipient.estado
            codes = []
            if recipient.message_id:
                event = db.query(CostEvent).filter_by(external_key='meta:' + recipient.message_id).first()
                receipts = db.query(MetaDeliveryReceipt).filter_by(message_id=recipient.message_id).all()
                ranks = {'accepted': 0, 'sent': 1, 'delivered': 2, 'read': 3, 'failed': 4}
                states = [r.status for r in receipts] + ([event.status] if event else [])
                if states:
                    state = max(states, key=lambda s: ranks.get(s, -1))
                codes = sorted({e['code'] for r in receipts for e in json.loads(r.errors_json) if e.get('code')})
            result.append({'telefono': '…' + recipient.telefono[-4:], 'estado': state,
                           'codigos_meta': codes, 'detalle': recipient.detalle})
        return {'id': key, 'estado': batch.estado, 'detalle': batch.detalle,
                'desde_utc': batch.desde.isoformat() + 'Z' if batch.desde else None,
                'hasta_utc': batch.hasta.isoformat() + 'Z' if batch.hasta else None,
                'resumen': dict(Counter(r['estado'] for r in result)), 'destinatarios': result,
                'envio': 'Un destinatario por minuto; sin reintentos automáticos'}


async def send_recipient(phone, row, name, operator, request_id):
    # Reuse the panel's durable request reservation, media upload and history.
    from app.api.panel import _enviar_inicio_chat
    values = [name]
    canonical = json.dumps({'plantilla': row, 'telefono': phone, 'valores': values}, sort_keys=True, ensure_ascii=False)
    return await _enviar_inicio_chat(phone, {'request_id': request_id, 'mensaje': canonical,
        'plantilla': row, 'texto': templates.render(row, values), 'valores': values}, operator)


async def run_due():
    now = now_utc()
    with SessionSesiones() as db:
        # A claimed row is never returned to the queue after a crash.
        db.query(PilotRecipient).filter(PilotRecipient.estado == 'en_proceso', PilotRecipient.intento_en < now - timedelta(minutes=5)).update(
            {'estado': 'incierta', 'detalle': 'Proceso interrumpido. Revisar antes de cualquier nuevo envío.'})
        db.commit()
        keys = [b.id for b in db.query(PilotBatch).filter(PilotBatch.estado == 'activa', PilotBatch.desde <= now)]
    # At most one attempted recipient per invocation; each batch also holds a
    # persisted minute slot so overlapping scheduler workers cannot drain it.
    for key in keys:
        snapshot = report(key)
        states = snapshot['resumen']
        if states.get('incierta') or states.get('failed', 0) >= 3:
            pause(key, 'Revisar resultado incierto o tres fallos de Meta. No se reintenta automáticamente.')
            continue
        with SessionSesiones() as db:
            batch = db.get(PilotBatch, key)
            if batch.hasta < now:
                batch.estado = 'vencida'; db.commit(); continue
            recipient = db.query(PilotRecipient).filter_by(lote=key, estado='pendiente').order_by(PilotRecipient.id).first()
            if not recipient:
                if not db.query(PilotRecipient).filter_by(lote=key, estado='en_proceso').first():
                    batch.estado = 'procesada'; db.commit()
                continue
            phone, name, row, operator, rid = recipient.telefono, recipient.nombre, json.loads(batch.plantilla_json), batch.operador, recipient.id
        try:
            live = await current_template()
            if live['huella'] != row['huella']:
                raise ValueError('La plantilla cambió desde la preparación')
        except Exception:
            pause(key, 'No se pudo verificar la plantilla aprobada. No se enviaron más mensajes.')
            continue
        with SessionSesiones() as db:
            # Atomic claim includes the batch state in case it was paused during lookup.
            slot = db.query(PilotBatch).filter(PilotBatch.id == key, PilotBatch.estado == 'activa',
                (PilotBatch.siguiente_intento.is_(None)) | (PilotBatch.siguiente_intento <= now)).update(
                    {'siguiente_intento': now + timedelta(minutes=1)}, synchronize_session=False)
            if not slot:
                db.rollback()
                continue
            active = db.query(PilotBatch.id).filter_by(id=key, estado='activa').exists()
            claimed = db.query(PilotRecipient).filter(PilotRecipient.id == rid, PilotRecipient.estado == 'pendiente', active).update(
                {'estado': 'en_proceso', 'intento_en': now}, synchronize_session=False)
            db.commit()
        if not claimed:
            continue
        try:
            session = obtener_sesion_existente(phone)
            if is_suppressed(phone) or (session and (session.atencion_humana_directa or session.necesita_atencion_humana)):
                state, detail, message_id = 'omitida', 'Baja o atención en curso; no se envió.', None
            else:
                result = await send_recipient(phone, row, name, operator, f'pilot-{key}-{rid}')
                state, detail, message_id = result.get('estado', 'accepted'), None, result['message_id']
        except Exception:
            state, detail, message_id = 'incierta', 'Revisar diagnóstico e historial. No se reenvía automáticamente.', None
            pause(key, detail)
        with SessionSesiones() as db:
            db.query(PilotRecipient).filter_by(id=rid).update({'estado': state, 'detalle': detail, 'message_id': message_id})
            db.commit()
        return  # At most one attempted recipient per scheduler tick.


def main():
    parser = argparse.ArgumentParser(description='Preparar y activar un piloto de hasta 10 WhatsApp, sin duplicados ni reintentos')
    commands = parser.add_subparsers(dest='action', required=True)
    prep = commands.add_parser('preparar')
    prep.add_argument('--id', required=True)
    prep.add_argument('--csv')
    prep.add_argument('--operador', default='alexander')
    prep.add_argument('--cantidad', type=int, default=10)
    prep.add_argument('--confirmo-permiso-whatsapp', action='store_true')
    arm = commands.add_parser('activar')
    arm.add_argument('--id', required=True)
    timing = arm.add_mutually_exclusive_group(required=True)
    timing.add_argument('--cuando')
    timing.add_argument('--ahora', action='store_true')
    for action in ('resumen', 'pausar'):
        commands.add_parser(action).add_argument('--id', required=True)
    args = parser.parse_args()
    try:
        if args.action == 'preparar':
            result = asyncio.run(prepare(args.id, read_source(args.csv), args.operador, args.cantidad, args.confirmo_permiso_whatsapp))
        elif args.action == 'activar':
            when = datetime.now(timezone.utc) if args.ahora else datetime.fromisoformat(args.cuando)
            result = asyncio.run(activate(args.id, when))
        elif args.action == 'pausar':
            pause(args.id); result = report(args.id)
        else:
            result = report(args.id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, TypeError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    main()
