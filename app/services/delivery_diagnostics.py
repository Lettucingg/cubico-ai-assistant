"""Persist Meta delivery receipts independently of local conversation history."""
import argparse
import hashlib
import json
import logging
import re
from datetime import datetime

from sqlalchemy import Column,DateTime,Integer,String,Text
from sqlalchemy.exc import IntegrityError
from app.db.session_store import BaseSesiones,SessionSesiones,engine_sesiones

LOG=logging.getLogger(__name__)


class MetaDeliveryReceipt(BaseSesiones):
    __tablename__='meta_delivery_receipts'
    id=Column(Integer,primary_key=True)
    dedupe_key=Column(String(64),nullable=False,unique=True)
    message_id=Column(String(300),nullable=False,index=True)
    phone=Column(String(40),nullable=False,default='',index=True)
    status=Column(String(30),nullable=False)
    meta_timestamp=Column(String(30),nullable=False,default='')
    errors_json=Column(Text,nullable=False,default='[]')
    received_at=Column(DateTime,nullable=False,default=datetime.utcnow)


MetaDeliveryReceipt.__table__.create(engine_sesiones,checkfirst=True)


def bounded(value,limit):
    return str(value or '')[:limit]


def record_receipt(receipt):
    if not receipt.get('id'):return
    errors=[]
    for error in (receipt.get('errors') or [])[:10]:
        if not isinstance(error,dict):continue
        data=error.get('error_data') or {}
        errors.append({'code':bounded(error.get('code'),30),
                       'title':bounded(error.get('title'),200),
                       'message':bounded(error.get('message'),500),
                       'details':bounded(data.get('details') if isinstance(data,dict) else '',1000)})
    values=dict(message_id=bounded(receipt['id'],300),phone=bounded(receipt.get('recipient_id'),40),
                status=bounded(receipt.get('status'),30),meta_timestamp=bounded(receipt.get('timestamp'),30),
                errors_json=json.dumps(errors,ensure_ascii=False,sort_keys=True))
    key=hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()
    try:
        with SessionSesiones() as db:
            db.add(MetaDeliveryReceipt(dedupe_key=key,**values));db.commit()
    except IntegrityError:
        return  # Duplicate webhooks must not duplicate the diagnosis.
    if values['status']=='failed':
        LOG.warning('Fallo de entrega Meta: destinatario …%s; códigos=%s',values['phone'][-4:],
                    ','.join(e['code'] for e in errors) or 'sin código recibido')


def diagnostics(phone,limit=10):
    number=re.sub(r'[ +()\-]','',phone)
    if not re.fullmatch(r'[1-9][0-9]{7,14}',number):raise ValueError('Indica el número internacional completo')
    from app.services.cost_analytics import CostEvent
    with SessionSesiones() as db:
        events=db.query(CostEvent).filter_by(provider='meta',phone=number).order_by(CostEvent.created_at.desc(),CostEvent.id.desc()).limit(limit).all()
        result=[]
        keys=[]
        for event in events:
            key=(event.external_key or '').removeprefix('meta:')
            if not key:continue
            keys.append(key)
            receipts=db.query(MetaDeliveryReceipt).filter_by(message_id=key).order_by(MetaDeliveryReceipt.id.desc()).limit(20).all()
            result.append({'message_id':key,'estado_actual':event.status,'fecha_envio_utc':event.created_at.isoformat(),
                           'recibos':[_serialize(r) for r in receipts],
                           'nota':None if receipts else 'No se conservó el detalle de este envío. Un fallo anterior a la actualización no se puede reconstruir con estos registros.'})
        # Preserve evidence even if the independent cost ledger could not be written.
        extra=db.query(MetaDeliveryReceipt).filter_by(phone=number)
        if keys:extra=extra.filter(~MetaDeliveryReceipt.message_id.in_(keys))
        for row in extra.order_by(MetaDeliveryReceipt.id.desc()).limit(limit):
            result.append({'message_id':row.message_id,'estado_actual':None,'recibos':[_serialize(row)],
                           'nota':'Sin registro de coste asociado; se muestra el recibo de Meta.'})
        return {'telefono':'…'+number[-4:],'envios':result[:limit],'solo_consulta':True}


def _serialize(row):
    return {'estado':row.status,'fecha_meta_unix':row.meta_timestamp,'recibido_utc':row.received_at.isoformat(),
            'errores':json.loads(row.errors_json)}


def main():
    parser=argparse.ArgumentParser(description='Consulta estados y errores de Meta sin enviar ni reintentar mensajes')
    parser.add_argument('--telefono',required=True)
    args=parser.parse_args()
    try:print(json.dumps(diagnostics(args.telefono),ensure_ascii=False,indent=2))
    except ValueError as error:parser.exit(2,str(error)+'\n')


if __name__=='__main__':main()
