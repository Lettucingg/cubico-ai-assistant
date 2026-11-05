"""Persistent Lynn inbox and Luis-only confirmation workflow.

No registration happens during collection/extraction. Claimed registrations are
never replayed after a crash, including unknown HTTP outcomes.
"""
import json
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.db.session_store import BaseSesiones, SessionSesiones, engine_sesiones
from app.services import china_air_client as api
from app.services.china_air_extraction import extract

BUSY = {'processing', 'confirming', 'saving'}


class ChinaAirBatch(BaseSesiones):
    __tablename__ = 'china_air_batches'
    id = Column(String(36), primary_key=True)
    phone = Column(String(40), nullable=False, index=True)
    stage = Column(String(30), nullable=False, default='collecting')
    closed = Column(Boolean, nullable=False, default=False)
    version = Column(Integer, nullable=False, default=0)
    due = Column(DateTime, nullable=False)
    updated = Column(DateTime, nullable=False)
    prompt_sent = Column(DateTime, nullable=True)
    packages_json = Column(Text, nullable=True)
    preview_json = Column(Text, nullable=True)
    warnings_json = Column(Text, nullable=False, default='[]')
    results_json = Column(Text, nullable=True)
    detail = Column(String(500), nullable=True)


Index('china_air_one_active_phone', ChinaAirBatch.phone, unique=True,
      sqlite_where=ChinaAirBatch.closed.is_(False), postgresql_where=ChinaAirBatch.closed.is_(False))


class ChinaAirInbox(BaseSesiones):
    __tablename__ = 'china_air_inbox'
    id = Column(Integer, primary_key=True)
    message_id = Column(String(300), unique=True, nullable=False)
    phone = Column(String(40), nullable=False, index=True)
    kind = Column(String(20), nullable=False)
    body = Column(Text, nullable=False, default='')
    media_id = Column(String(300), nullable=True)
    received = Column(DateTime, nullable=False)
    batch_id = Column(String(36), nullable=True, index=True)


for model in (ChinaAirBatch, ChinaAirInbox):
    model.__table__.create(engine_sesiones, checkfirst=True)


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def clean(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', value.lower()) if not unicodedata.combining(c)).split())


def enabled():
    return settings.CUBICO_CHINA_AIR_ENABLED and bool(settings.CUBICO_BOT_KEY.strip()) and bool(api.luis_numbers())


def should_handle(message):
    if message.get('telefono') not in api.luis_numbers() or not enabled():
        return False
    if message.get('tipo') not in {'text', 'image'}:
        return False
    value = clean(message.get('texto') or '')
    if value.startswith('/') and not value.startswith('/china'):
        return False  # Preserve the team's existing operational commands.
    if message.get('tipo') == 'image' or value.startswith('/china') or (
            ('china' in value and 'aereo' in value and any(word in value for word in ('recib', 'bodega', 'lynn')))
            or 'peso fisico' in value):
        return True
    with SessionSesiones() as db:
        return (db.query(ChinaAirBatch.id).filter_by(phone=message['telefono'], closed=False).first() is not None
                or db.query(ChinaAirInbox.id).filter_by(phone=message['telefono'], batch_id=None).first() is not None)


def enqueue(message):
    """Durably accept the raw messages BEFORE returning a webhook 200."""
    if message.get('telefono') not in api.luis_numbers() or not enabled():
        raise ValueError('No autorizado o integración deshabilitada')
    if message.get('tipo') not in {'text', 'image'} or not message.get('message_id'):
        raise ValueError('Reenvía textos y fotos, con identificador de WhatsApp')
    value = str(message.get('texto') or '')
    if len(value) > 12000:
        raise ValueError('Texto demasiado largo para este lote')
    with SessionSesiones() as db:
        db.add(ChinaAirInbox(message_id=message['message_id'], phone=message['telefono'], kind=message['tipo'],
            body=value, media_id=message.get('media_id'), received=now_utc()))
        try:
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            return False


def update(batch_id, expected_stage=None, expected_version=None, **fields):
    with SessionSesiones() as db:
        query = db.query(ChinaAirBatch).filter_by(id=batch_id)
        if expected_stage is not None:
            query = query.filter_by(stage=expected_stage)
        if expected_version is not None:
            query = query.filter_by(version=expected_version)
        changed = query.update({**fields, 'updated': now_utc(), 'version': ChinaAirBatch.version + 1}, synchronize_session=False)
        db.commit()
        return bool(changed)


def snapshot(batch_id):
    with SessionSesiones() as db:
        row = db.get(ChinaAirBatch, batch_id)
        return {column.name: getattr(row, column.name) for column in ChinaAirBatch.__table__.columns} if row else None


async def tell(phone, text):
    # The only WhatsApp destination of this module is an authorized Luis number.
    if phone not in api.luis_numbers():
        raise ValueError('Destino no autorizado')
    from app.api.whatsapp import enviar_mensaje_whatsapp, extraer_id_mensaje_meta
    from app.db.session_store import obtener_o_crear_sesion, agregar_al_historial
    for start in range(0, len(text), 3300):
        part = text[start:start + 3300]
        response = await enviar_mensaje_whatsapp(phone, part)
        mid = extraer_id_mensaje_meta(response)
        if not response.is_success or not mid:
            raise ValueError('No se confirmó la entrega del resumen a Luis')
        obtener_o_crear_sesion(phone)
        agregar_al_historial(phone, 'assistant', part, whatsapp_message_id=mid, estado_entrega='accepted',
            contexto_ia='[Operación interna China aéreo para Luis, no es una respuesta de cliente.] ' + part)


async def show_preview(batch_id, packages, rows, warnings):
    state = snapshot(batch_id)
    if not state:
        return
    # Keep the draft busy until the entire summary has been accepted by Meta.
    await tell(state['phone'], api.summary(packages, rows, warnings))
    update(batch_id, expected_stage=state['stage'], expected_version=state['version'],
           **{'stage': 'awaiting', 'prompt_sent': now_utc(), 'packages_json': json.dumps(packages),
              'preview_json': json.dumps(rows), 'warnings_json': json.dumps(warnings), 'detail': None})


def corrections(value, packages):
    """Explicit confirmation and deterministic client corrections only."""
    value = clean(value)
    confirm = bool(re.match(r'^(?:si|confirmo|registrar|registralos)(?:\b|[, .])', value))
    tail = re.sub(r'^(?:si|confirmo|registrar|registralos)[, .:]*', '', value) if confirm else value
    copied = [dict(p) for p in packages]
    if not tail:
        return confirm, copied
    if re.fullmatch(r'(?:cbc[ -]*)?\d{1,8}|[a-z][a-z0-9_-]{1,19}', tail):
        missing = [p for p in copied if not p.get('cliente')]
        if not missing:
            raise ValueError('No hay clientes pendientes. Indica el número del paquete para cambiar un código: «2 CBC-0093».')
        code = api.Package(cliente=tail).cliente
        for package in missing:
            package['cliente'] = code
        return confirm, copied
    parts = re.split(r'\s*[;,]\s*', tail)
    seen = set()
    for part in parts:
        match = re.fullmatch(r'(?:paquete\s+)?(\d{1,2})\s+(?:es\s+de\s+)?([a-z0-9 -]+)', part)
        if not match:
            raise ValueError('Para corregir: «2 CBC-0093; 3 CBC-0093». Después confirma con «sí».')
        index = int(match[1]) - 1
        if not 0 <= index < len(copied) or index in seen:
            raise ValueError('Número de paquete inválido o repetido')
        seen.add(index)
        copied[index]['cliente'] = api.Package(cliente=match[2]).cliente
    return confirm, copied


def quote_identity(rows):
    return [{key: (row.get('paquete') or {}).get(key) for key in
             ('tracking', 'cliente', 'lb_reales', 'lb_volumen', 'lb_cobrables', 'tarifa_cliente', 'cobro_estimado')}
            | {'ok': row['ok'], 'errores': row.get('errores'), 'avisos': row.get('avisos')} for row in rows]


async def confirm_batch(batch_id, value):
    state = snapshot(batch_id)
    try:
        packages = json.loads(state['packages_json'])
        confirm, corrected = corrections(value, packages)
        corrected = api.validate_packages(corrected)
        rows = await api.preview(corrected)
        warnings = json.loads(state['warnings_json'])
        if (not confirm or api.missing_fields(corrected) or not all(row['ok'] for row in rows) or
                (corrected == packages and quote_identity(rows) != quote_identity(json.loads(state['preview_json'])))):
            await show_preview(batch_id, corrected, rows, warnings)
            return
    except Exception:
        update(batch_id, expected_stage='confirming', **{'stage': 'needs_input', 'detail': 'No se pudo validar la confirmación. No se registró nada.'})
        await tell(state['phone'], 'No pude validar el lote o la corrección. No registré nada. Usa «/china estado» para revisar o «/china cancelar» para reenviar el aviso completo.')
        return
    if not update(batch_id, expected_stage='confirming', **{'stage': 'saving', 'packages_json': json.dumps(corrected), 'preview_json': json.dumps(rows)}):
        return
    try:
        results = await api.register(corrected, phone=state['phone'])
    except Exception:
        update(batch_id, expected_stage='saving', **{'stage': 'uncertain', 'detail': 'Resultado del registro incierto; no repetir sin revisar Cúbico.'})
        await tell(state['phone'], '⚠️ No pude confirmar el resultado del registro. Puede haberse guardado parte o todo. Revisa Cúbico antes de repetir; no lo reenviaré automáticamente.')
        return
    update(batch_id, expected_stage='saving', **{'stage': 'done', 'closed': True, 'results_json': json.dumps(results), 'detail': None})
    successful = [package for package, result in zip(corrected, results) if result['registrado']]
    lines = [f'✅ Cúbico confirmó {len(successful)} de {len(corrected)} paquetes registrados.']
    for package, result in zip(corrected, results):
        if result['registrado']:
            mail = 'Cúbico indica correo enviado' if result.get('aviso_enviado') is True else 'correo no confirmado como enviado'
            lines.append(f"✓ {package['tracking']} · {package['cliente']} · {mail}")
        else:
            lines.append(f"⚠️ {package['tracking']}: {api.safe_text(result.get('errores') or 'no se registró')}")
    if len(successful) == len(corrected):
        lines.append('Para Lynn (texto para que lo envíes tú): «Sí, continuar con el envío de estos paquetes: ' +
                     ', '.join(package['tracking'] for package in successful) + '.»')
    else:
        lines.append('No confirmes el lote completo a Lynn: revisa primero los paquetes que no se registraron.')
    await tell(state['phone'], '\n'.join(lines))


async def analyze(batch_id):
    state = snapshot(batch_id)
    with SessionSesiones() as db:
        messages = [{'texto': row.body, 'media_id': row.media_id} for row in db.query(ChinaAirInbox).filter_by(
            batch_id=batch_id).order_by(ChinaAirInbox.id)]
    try:
        if len(messages) > 60:
            raise ValueError('Demasiados mensajes; divide el lote')
        packages, warnings = await extract(messages, state['phone'])
        rows = await api.preview(packages)
        with SessionSesiones() as db:
            pending = db.query(ChinaAirInbox).filter_by(phone=state['phone'], batch_id=None).first()
        if pending:
            update(batch_id, expected_stage='processing', **{'stage': 'collecting', 'due': now_utc() + timedelta(seconds=120)})
            return
        await show_preview(batch_id, packages, rows, warnings)
    except Exception:
        update(batch_id, expected_stage='processing', **{'stage': 'needs_input', 'detail': 'Lectura o previsualización incompleta; no se registró nada.'})
        await tell(state['phone'], 'No pude completar la lectura y previsualización de este aviso. No registré nada. Revisa que estén todas las fotos, el texto aéreo y los datos legibles. Puedes añadir lo que falta o usar «/china cancelar» y reenviar un lote más pequeño. Revisa también la conexión local de Cúbico.')


async def consume_one(phone):
    action = None
    with SessionSesiones() as db:
        message = db.query(ChinaAirInbox).filter_by(phone=phone, batch_id=None).order_by(ChinaAirInbox.id).first()
        if not message:
            return False
        batch = db.query(ChinaAirBatch).filter_by(phone=phone, closed=False).first()
        if batch and batch.stage in BUSY:
            return False
        value = clean(message.body)
        if not batch and value in {'/china estado', '/china', '/china cancelar', '/china revisado'}:
            previous = db.query(ChinaAirBatch).filter_by(phone=phone).order_by(ChinaAirBatch.updated.desc()).first()
            if not previous:
                previous = ChinaAirBatch(id=str(uuid.uuid4()), phone=phone, stage='info', closed=True,
                                         due=now_utc(), updated=now_utc())
                db.add(previous); db.flush()
            claimed = db.query(ChinaAirInbox).filter_by(message_id=message.message_id, batch_id=None).update({'batch_id': previous.id})
            if not claimed:
                db.rollback(); return False
            notice = (f'Último lote {previous.id[:8]} · estado: {previous.stage}. ' + (previous.detail or '') +
                      ' Reenvía las fotos y textos de Lynn para iniciar un lote nuevo. No se registra nada hasta tu confirmación.')
            db.commit()
            await tell(phone, notice)
            return True
        if not batch:
            batch = ChinaAirBatch(id=str(uuid.uuid4()), phone=phone, due=now_utc() + timedelta(seconds=120), updated=now_utc())
            db.add(batch)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                return False
            action = ('notice', 'Estoy reuniendo las fotos y textos del aviso de China aéreo. Esperaré unos dos minutos desde el último mensaje antes de mostrarte el resumen. No registraré nada sin tu confirmación.')
        bid, version, stage = batch.id, batch.version, batch.stage
        fields = {'version': version + 1, 'updated': now_utc()}
        if value in {'/china estado', '/china'}:
            action = ('notice', f'Lote {bid[:8]} · estado: {stage}. ' + (batch.detail or '') +
                      (' Responde «sí» solo después de revisar el resumen.' if stage == 'awaiting' else ''))
            if batch.packages_json and batch.preview_json:
                action = ('notice', action[1] + '\n' + api.summary(json.loads(batch.packages_json),
                    json.loads(batch.preview_json), json.loads(batch.warnings_json)))
        elif value == '/china revisado' and stage == 'uncertain':
            fields.update(stage='reviewed', closed=True, detail='Luis confirmó revisión manual en Cúbico; sin repetir registros.')
            action = ('notice', 'Marcaste el lote como revisado manualmente en Cúbico. No repetí ningún registro. Ya puedes reenviar un lote nuevo.')
        elif value in {'cancelar', 'no', '/china cancelar'}:
            if stage == 'uncertain':
                action = ('notice', 'El resultado es incierto: revisa Cúbico antes de iniciar otro lote. Este registro no se repetirá automáticamente.')
            else:
                fields.update(stage='cancelled', closed=True)
                action = ('notice', 'Lote cancelado. No se registró nada por esta confirmación.')
        elif stage == 'uncertain':
            action = ('notice', 'El registro anterior sigue con resultado incierto. Revisa Cúbico; no voy a repetirlo ni abrir otro lote automáticamente.')
        elif stage == 'awaiting' and message.kind == 'text':
            if batch.prompt_sent and message.received <= batch.prompt_sent:
                action = ('notice', 'Ese mensaje llegó antes de terminar el resumen. Revísalo y responde «sí» de nuevo si deseas registrar este lote.')
            else:
                try:
                    corrections(message.body, json.loads(batch.packages_json))
                    fields['stage'] = 'confirming'
                    action = ('confirm', message.body)
                except ValueError:
                    fields.update(stage='collecting', due=message.received + timedelta(seconds=120), prompt_sent=None)
                    action = ('notice', 'Añadí tu aclaración al lote. Volveré a revisarlo antes de pedir confirmación.')
        else:
            fields.update(stage='collecting', due=message.received + timedelta(seconds=120), prompt_sent=None)
        claimed = db.query(ChinaAirBatch).filter_by(id=bid, version=version).update(fields, synchronize_session=False)
        if not claimed:
            db.rollback()
            return False
        # A second worker must claim the same input, not merely the batch.
        claimed_message = db.query(ChinaAirInbox).filter_by(message_id=message.message_id, batch_id=None).update({'batch_id': bid})
        if not claimed_message:
            db.rollback()
            return False
        db.commit()
    if action:
        if action[0] == 'confirm':
            await confirm_batch(bid, action[1])
        else:
            await tell(phone, action[1])
    return True


async def run_due():
    if not enabled():
        return
    now = now_utc()
    with SessionSesiones() as db:
        stale = db.query(ChinaAirBatch).filter(ChinaAirBatch.closed.is_(False), ChinaAirBatch.stage.in_(BUSY),
                                             ChinaAirBatch.updated < now - timedelta(minutes=10)).all()
        alerts = []
        for row in stale:
            row.stage = 'uncertain' if row.stage in {'confirming', 'saving'} else 'needs_input'
            row.detail = 'Proceso interrumpido; revisar antes de continuar, sin reintento automático.'
            row.updated = now; row.version += 1
            alerts.append(row.phone)
        db.commit()
    for phone in alerts:
        try:
            await tell(phone, '⚠️ El proceso de China aéreo se interrumpió. Revisa Cúbico antes de repetir cualquier registro; no se reintentará automáticamente.')
        except Exception:
            pass
    for phone in sorted(api.luis_numbers()):
        try:
            for _ in range(60):
                if not await consume_one(phone):
                    break
            with SessionSesiones() as db:
                batch = db.query(ChinaAirBatch).filter(ChinaAirBatch.phone == phone, ChinaAirBatch.closed.is_(False),
                    ChinaAirBatch.stage == 'collecting', ChinaAirBatch.due <= now_utc()).first()
                bid, version = (batch.id, batch.version) if batch else (None, None)
            if bid and update(bid, expected_stage='collecting', expected_version=version, **{'stage': 'processing'}):
                await analyze(bid)
        except Exception:
            # Preserve inbox/draft and never dump model output, key, or HTTP headers.
            import logging
            logging.getLogger(__name__).error('China aéreo: revisar lote interno; no se reintenta un registro incierto')
