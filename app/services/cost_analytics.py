"""Local cost ledger. Never treats an unknown price as free or rewrites history."""
import json
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from time import perf_counter
from zoneinfo import ZoneInfo

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text
from sqlalchemy.exc import IntegrityError
from app.db.session_store import BaseSesiones, SessionSesiones, UsoIA, engine_sesiones

PANAMA = ZoneInfo('America/Panama')
LOG = logging.getLogger(__name__)
# USD per million tokens, standard API. Snapshot retained per event.
RATES = {
    'claude-sonnet-5': ('2', '10', '2.5', '4', '.2'),
    'claude-sonnet-4-6': ('3', '15', '3.75', '6', '.3'),
    'claude-sonnet-4-5': ('3', '15', '3.75', '6', '.3'),
}
PRICING_DATE = '2026-10-08'

class CostEvent(BaseSesiones):
    __tablename__ = 'bot_cost_events'
    id = Column(Integer, primary_key=True)
    provider = Column(String(32), index=True, nullable=False)
    model = Column(String(120), nullable=False, default='')
    task = Column(String(80), index=True, nullable=False)
    phone = Column(String(40), index=True, nullable=False, default='')
    status = Column(String(32), nullable=False, default='ok')
    external_key = Column(String(300), unique=True, nullable=True)
    legacy_id = Column(Integer, unique=True, nullable=True)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    cache_read = Column(Integer, default=0, nullable=False)
    cache_write = Column(Integer, default=0, nullable=False)
    audio_seconds = Column(Numeric(20, 6), nullable=True)
    cost = Column(Numeric(20, 10), nullable=True)
    elapsed_ms = Column(Integer, nullable=True)
    pricing_json = Column(Text, nullable=False, default='{}')
    created_at = Column(DateTime, index=True, nullable=False, default=datetime.utcnow)

class ConfirmedExpense(BaseSesiones):
    __tablename__ = 'bot_confirmed_expenses'
    id = Column(Integer, primary_key=True)
    request_id = Column(String(80), unique=True, nullable=False)
    provider = Column(String(32), nullable=False)
    concept = Column(String(160), nullable=False)
    reference = Column(String(100), nullable=False, default='')
    expense_date = Column(String(10), index=True, nullable=False)
    amount = Column(Numeric(20, 6), nullable=False)
    user = Column(String(80), nullable=False)
    archived = Column(Boolean, default=False, nullable=False)
    modified_by = Column(String(80), nullable=True)
    modified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

for table in (CostEvent.__table__, ConfirmedExpense.__table__):
    table.create(engine_sesiones, checkfirst=True)


def _get(obj, key, default=0):
    return (obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)) or default


def record_event(**values):
    """Accounting failures must not block replies. Metadata contains no message text."""
    try:
        with SessionSesiones() as db:
            event = CostEvent(**values)
            db.add(event)
            db.commit()
    except IntegrityError:
        # Provider ID can arrive again in webhook retries.
        return
    except Exception:
        LOG.exception('No se pudo registrar una métrica de costos')


def record_anthropic(response, phone='', task='respuesta_automatica', elapsed_ms=None):
    usage = getattr(response, 'usage', None)
    model = getattr(response, 'model', '') or ''
    inp, out = int(_get(usage, 'input_tokens')), int(_get(usage, 'output_tokens'))
    read, write = int(_get(usage, 'cache_read_input_tokens')), int(_get(usage, 'cache_creation_input_tokens'))
    cache = _get(usage, 'cache_creation', {})
    hour = int(_get(cache, 'ephemeral_1h_input_tokens'))
    five = int(_get(cache, 'ephemeral_5m_input_tokens', max(0, write-hour)))
    rates = next((v for k, v in RATES.items() if model == k or model.startswith(k+'-20')), None)
    cost = None
    snapshot = {'verified_at': PRICING_DATE, 'source': 'https://platform.claude.com/docs/en/about-claude/pricing', 'cache_write_5m': five, 'cache_write_1h': hour}
    if usage is not None and rates and hour + five == write:
        a,b,c,d,e = map(Decimal, rates)
        cost = (inp*a + out*b + five*c + hour*d + read*e) / Decimal(1000000)
        snapshot['usd_per_million'] = dict(zip(('input','output','write_5m','write_1h','read'), rates))
    try:
        with SessionSesiones() as db:
            # Legacy consumers receive complete input (including cache) and updated cost.
            legacy = None
            if cost is not None:
                legacy = UsoIA(telefono=phone, modelo=model, input_tokens=inp+read+write, output_tokens=out, costo_usd=float(cost))
                db.add(legacy)
                db.flush()
            db.add(CostEvent(provider='anthropic', model=model, task=task, phone=phone,
                external_key=('anthropic:'+str(response.id)) if getattr(response, 'id', None) else None,
                legacy_id=legacy.id if legacy else None, input_tokens=inp, output_tokens=out,
                cache_read=read, cache_write=write, cost=cost, elapsed_ms=elapsed_ms,
                pricing_json=json.dumps(snapshot)))
            db.commit()
    except IntegrityError:
        pass
    except Exception:
        LOG.exception('No se pudo registrar el uso de Anthropic')


def call_anthropic(client, *, phone='', task='respuesta_automatica', **kwargs):
    start = perf_counter()
    try:
        response = client.messages.create(**kwargs)
    except Exception:
        record_event(provider='anthropic', model=kwargs.get('model',''), task=task, phone=phone, status='error', elapsed_ms=int((perf_counter()-start)*1000))
        raise
    try:
        record_anthropic(response, phone, task, int((perf_counter()-start)*1000))
    except Exception:
        LOG.exception('Respuesta válida de IA con métricas ilegibles')
    return response


def record_whatsapp_response(response, phone, kind):
    try:
        msgid = response.json().get('messages', [{}])[0].get('id') if response.is_success else None
    except (ValueError, IndexError, TypeError, AttributeError):
        msgid = None
    if msgid:
        try:
            with SessionSesiones() as db:
                existing = db.query(CostEvent).filter_by(external_key='meta:'+msgid).first()
                if existing:
                    existing.task = 'mensaje_'+kind
                    existing.phone = phone
                    db.commit()
                    return
        except Exception:
            LOG.exception('No se pudo completar el registro de WhatsApp')
    record_event(provider='meta', model='whatsapp', task='mensaje_'+kind, phone=phone,
                 status='accepted' if response.is_success else 'failed', external_key='meta:'+msgid if msgid else None)


def record_whatsapp_receipts(payload):
    # Process every receipt, even when Meta batches them or a receipt beats HTTP return.
    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            for receipt in change.get('value', {}).get('statuses', []):
                key = receipt.get('id')
                if not key:
                    continue
                try:
                    with SessionSesiones() as db:
                        event = db.query(CostEvent).filter_by(external_key='meta:'+key).first()
                        if event is None:
                            event = CostEvent(provider='meta', model='whatsapp', task='mensaje_tipo_desconocido', phone=receipt.get('recipient_id',''), external_key='meta:'+key)
                            stamp = receipt.get('timestamp')
                            if stamp:
                                event.created_at = datetime.fromtimestamp(int(stamp), timezone.utc).replace(tzinfo=None)
                            db.add(event)
                        status = receipt.get('status','accepted')
                        rank = {'accepted':0,'sent':1,'delivered':2,'read':3,'failed':4}
                        if rank.get(status,0) >= rank.get(event.status or 'accepted',0):
                            event.status = status
                        pricing = receipt.get('pricing') or {}
                        if pricing:
                            event.pricing_json = json.dumps(pricing)
                            if pricing.get('billable') is False:
                                event.cost = Decimal(0)
                        db.commit()
                except Exception:
                    LOG.exception('No se pudo registrar el recibo de WhatsApp')


def save_expense(body, user):
    # The caller validates through Pydantic. No invoice is added to estimated usage.
    with SessionSesiones() as db:
        old = db.query(ConfirmedExpense).filter_by(request_id=body.request_id).first()
        values = dict(provider=body.proveedor, concept=body.concepto.strip(), reference=body.referencia.strip(), expense_date=body.fecha.isoformat(), amount=body.monto_usd)
        if old:
            if any(getattr(old,k) != v for k,v in values.items()):
                raise ValueError('Este identificador ya corresponde a otro gasto')
            return old.id
        row = ConfirmedExpense(**values, user=user, request_id=body.request_id)
        db.add(row)
        db.commit()
        return row.id


def _utc(day):
    return datetime.combine(day, time.min, PANAMA).astimezone(timezone.utc).replace(tzinfo=None)


def _empty():
    return dict(costo_usd=0., eventos=0, llamadas_ia=0, mensajes=0, tokens=0, input_tokens=0, output_tokens=0, cache_read=0, cache_write=0, segundos_audio=0., sin_precio=0, errores=0, entregados=0)


def _add(bucket, row):
    bucket['eventos'] += 1
    bucket['costo_usd'] += float(row['cost'] or 0)
    bucket['sin_precio'] += row['cost'] is None
    bucket['llamadas_ia'] += row['provider'] in ('anthropic','openai')
    bucket['mensajes'] += row['provider'] == 'meta'
    bucket['errores'] += row['status'] in ('error','failed')
    bucket['entregados'] += row['provider'] == 'meta' and row['status'] in ('delivered','read')
    bucket['tokens'] += row['input_tokens']+row['output_tokens']+row['cache_read']+row['cache_write']
    bucket['input_tokens'] += row['input_tokens']+row['cache_read']+row['cache_write']
    bucket['output_tokens'] += row['output_tokens']
    bucket['cache_read'] += row['cache_read']
    bucket['cache_write'] += row['cache_write']
    bucket['segundos_audio'] += float(row['audio_seconds'] or 0)


def analytics(start, end, group='dia', provider='', task=''):
    if start > end or (end-start).days > 3660:
        raise ValueError('Selecciona un período de hasta diez años, con inicio anterior al fin')
    if group not in ('dia','mes','ano'):
        raise ValueError('Agrupación no válida')
    if provider and provider not in ('anthropic','openai','meta'):
        raise ValueError('Proveedor no válido')
    previous_end = start-timedelta(days=1)
    previous_start = previous_end-(end-start)
    with SessionSesiones() as db:
        events = db.query(CostEvent).filter(CostEvent.created_at >= _utc(previous_start), CostEvent.created_at < _utc(end+timedelta(days=1))).all()
        linked = db.query(CostEvent.legacy_id).filter(CostEvent.legacy_id.isnot(None))
        historical = db.query(UsoIA).filter(UsoIA.creado_en >= _utc(previous_start), UsoIA.creado_en < _utc(end+timedelta(days=1)), ~UsoIA.id.in_(linked)).all()
        rows = [{k:getattr(e,k) for k in ('provider','model','task','phone','status','input_tokens','output_tokens','cache_read','cache_write','audio_seconds','cost','created_at','elapsed_ms')} for e in events]
        rows += [dict(provider='anthropic',model=e.modelo,task='historico_sin_desglose',phone=e.telefono,status='ok',input_tokens=e.input_tokens,output_tokens=e.output_tokens,cache_read=0,cache_write=0,audio_seconds=None,cost=e.costo_usd,created_at=e.creado_en,elapsed_ms=None) for e in historical]
        expenses = db.query(ConfirmedExpense).filter(ConfirmedExpense.expense_date >= start.isoformat(), ConfirmedExpense.expense_date <= end.isoformat()).order_by(ConfirmedExpense.expense_date.desc(), ConfirmedExpense.id.desc()).all()
        expense_rows = [dict(id=e.id,proveedor=e.provider,concepto=e.concept,referencia=e.reference,fecha=e.expense_date,monto_usd=float(e.amount),usuario=e.user,archivado=e.archived) for e in expenses]
        first = db.query(CostEvent.created_at).order_by(CostEvent.created_at).first()
    selected, prev = [], []
    for row in rows:
        if (provider and row['provider'] != provider) or (task and row['task'] != task):
            continue
        row['day'] = row['created_at'].replace(tzinfo=timezone.utc).astimezone(PANAMA)
        (selected if row['day'].date() >= start else prev).append(row)
    totals, previous = _empty(), _empty()
    for row in selected: _add(totals,row)
    for row in prev: _add(previous,row)
    buckets = {}
    day = start
    while day <= end:
        key = day.isoformat() if group=='dia' else day.isoformat()[:7] if group=='mes' else str(day.year)
        buckets.setdefault(key,_empty())
        day += timedelta(days=1)
    breakdowns = {k:defaultdict(_empty) for k in ('provider','task','model','phone')}
    hours = [0]*24
    weekdays = [0]*7
    peaks = {k:defaultdict(_empty) for k in ('dia','mes','ano')}
    durations = []
    for row in selected:
        day = row['day']
        key = day.date().isoformat() if group=='dia' else day.strftime('%Y-%m') if group=='mes' else str(day.year)
        _add(buckets[key],row)
        for k in breakdowns: _add(breakdowns[k][row[k] or 'sin_asignar'],row)
        for k, key in (('dia',day.date().isoformat()),('mes',day.strftime('%Y-%m')),('ano',str(day.year))): _add(peaks[k][key],row)
        hours[day.hour] += 1
        weekdays[day.weekday()] += 1
        if row['elapsed_ms'] is not None and row['provider'] != 'meta': durations.append(row['elapsed_ms'])
    phones = {r['phone'] for r in selected if r['phone'] and r['provider'] != 'meta'}
    totals['conversaciones_ia'] = len(phones)
    totals['promedio_por_chat'] = sum(float(r['cost'] or 0) for r in selected if r['phone'] and r['provider'] != 'meta')/len(phones) if phones else None
    totals['latencia_media_ms'] = sum(durations)/len(durations) if durations else None
    def packed(mapping):
        return [dict(v, nombre=k, costo_usd=round(v['costo_usd'],8)) for k,v in sorted(mapping.items(),key=lambda item:(item[1]['costo_usd'],item[1]['eventos']),reverse=True)]
    expense_rows = [e for e in expense_rows if not provider or e['proveedor']==provider]
    return dict(desde=start.isoformat(),hasta=end.isoformat(),zona_horaria='America/Panama',agrupacion=group,
        totales=totals, anterior=dict(desde=previous_start.isoformat(),hasta=previous_end.isoformat(),**previous),
        serie=[dict(v, fecha=k, costo_usd=round(v['costo_usd'],8)) for k,v in sorted(buckets.items())],
        proveedores=packed(breakdowns['provider']),funciones=packed(breakdowns['task']),modelos=packed(breakdowns['model']),chats=packed(breakdowns['phone'])[:100],
        horas=hours,dias_semana=weekdays,picos={k:max((dict(fecha=x,**v) for x,v in mapping.items()),key=lambda x:x['eventos'],default=None) for k,mapping in peaks.items()},
        gastos_confirmados=expense_rows,total_confirmado=sum(e['monto_usd'] for e in expense_rows if not e['archivado']),
        seguimiento_detallado_desde=first[0].isoformat()+'Z' if first else None,
        historicos_sin_desglose=sum(r['task']=='historico_sin_desglose' for r in selected),
        tarifas_verificadas=PRICING_DATE)


def archive_expense(expense_id, archived, user):
    with SessionSesiones() as db:
        row = db.get(ConfirmedExpense, expense_id)
        if row is None:
            raise ValueError('No se encontró el gasto')
        row.archived = archived
        row.modified_by = user
        row.modified_at = datetime.utcnow()
        db.commit()
