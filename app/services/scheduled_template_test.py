"""One-off team tests. No prospect imports, recurring sends or automatic retries."""
import asyncio
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

import httpx
from app.core.config import settings
from app.db.session_store import SessionSesiones, PruebaPlantillaProgramada as TestSend


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def phone(value):
    value=re.sub(r'[ +()\-]', '', value)
    if not re.fullmatch(r'[1-9][0-9]{7,14}',value):
        raise ValueError('Usa el número internacional completo, incluido el código de país')
    return value


def allowed_recipient(value):
    recipients=json.loads(settings.CUBICO_TEST_RECIPIENTS_JSON)
    if not isinstance(recipients,list) or not all(isinstance(p,str) for p in recipients):
        raise ValueError('La lista de prueba debe ser una lista JSON de teléfonos')
    if value not in {phone(p) for p in recipients}:
        raise ValueError('El destinatario no está en la lista autorizada de pruebas')


def fingerprint(template):
    content={k:template[k] for k in ('name','language','category','components')}
    return hashlib.sha256(json.dumps(content,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def validate_template(template, values):
    if not isinstance(values,list):raise ValueError('Los valores deben ser una lista JSON')
    if template.get('status')!='APPROVED':
        raise ValueError('La plantilla no está aprobada: '+str(template.get('status','desconocido')))
    if template.get('category') not in {'UTILITY','MARKETING'}:
        raise ValueError('La prueba solo admite plantillas de utilidad o marketing')
    components=template.get('components',[])
    if any(c.get('type') not in {'BODY','FOOTER'} for c in components):
        raise ValueError('Esta prueba admite solo cuerpo de texto y pie, sin encabezados ni botones')
    bodies=[c for c in components if c.get('type')=='BODY']
    if len(bodies)!=1:raise ValueError('Debe existir un cuerpo de texto')
    text=bodies[0].get('text','')
    placeholders=set(re.findall(r'{{(.*?)}}',text))
    if placeholders!={str(i+1) for i in range(len(values))}:
        raise ValueError('Las variables deben ser numéricas y coincidir con los valores de prueba')
    if len(values)>5 or any(not isinstance(v,str) or not v.strip() or len(v)>300 for v in values):
        raise ValueError('Indica hasta cinco valores de texto no vacíos, de hasta 300 caracteres')
    return re.sub(r'{{([0-9]+)}}',lambda m:values[int(m[1])-1],text)


async def fetch_template(name,language):
    account=settings.WHATSAPP_BUSINESS_ACCOUNT_ID.strip()
    if not re.fullmatch(r'[0-9]+',account):raise ValueError('Falta WHATSAPP_BUSINESS_ACCOUNT_ID')
    async with httpx.AsyncClient(timeout=15) as client:
        response=await client.get(f'https://graph.facebook.com/v21.0/{account}/message_templates',
            headers={'Authorization':'Bearer '+settings.WHATSAPP_TOKEN},
            params={'name':name,'fields':'name,language,status,category,components','limit':100})
    if not response.is_success:raise ValueError('No se pudo comprobar la plantilla en Meta')
    matches=[t for t in response.json().get('data',[]) if t.get('name')==name and t.get('language')==language]
    if len(matches)!=1:raise ValueError('No se encontró una única plantilla con ese nombre e idioma')
    return matches[0]


async def schedule(key,recipient,name,language,values,when):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',key):raise ValueError('Identificador de prueba inválido')
    recipient=phone(recipient);allowed_recipient(recipient)
    if when.tzinfo is None:raise ValueError('La hora debe incluir zona horaria, por ejemplo -05:00')
    due=when.astimezone(timezone.utc).replace(tzinfo=None)
    if not now_utc()<due<=now_utc()+timedelta(days=7):raise ValueError('Programa dentro de los próximos siete días')
    template=await fetch_template(name,language)
    preview=validate_template(template,values)
    with SessionSesiones() as db:
        existing=db.get(TestSend,key)
        payload=(recipient,name,language,json.dumps(values),fingerprint(template),due)
        if existing:
            if (existing.telefono,existing.nombre,existing.idioma,existing.valores_json,existing.huella,existing.programada_en)!=payload:
                raise ValueError('El identificador ya existe con otros datos; no se modificó')
            return {'id':key,'estado':existing.estado,'vista_previa':preview}
        db.add(TestSend(id=key,telefono=recipient,nombre=name,idioma=language,valores_json=json.dumps(values),
                        huella=fingerprint(template),programada_en=due,estado='programada'))
        db.commit()
    return {'id':key,'estado':'programada','vista_previa':preview}


def list_tests():
    with SessionSesiones() as db:
        return [dict(id=r.id,telefono='…'+r.telefono[-4:],plantilla=r.nombre,idioma=r.idioma,
                     programada_en=r.programada_en.isoformat()+'Z',estado=r.estado,detalle=r.detalle,wamid=r.wamid)
                for r in db.query(TestSend).order_by(TestSend.programada_en.desc()).limit(50)]


def cancel(key):
    with SessionSesiones() as db:
        changed=db.query(TestSend).filter_by(id=key,estado='programada').update({'estado':'cancelada'})
        db.commit()
    if not changed:raise ValueError('Solo se puede cancelar una prueba todavía programada')


def finish(key,state,detail=None,wamid=None):
    with SessionSesiones() as db:
        db.query(TestSend).filter_by(id=key,estado='en_proceso').update(dict(estado=state,detalle=detail,wamid=wamid))
        db.commit()


async def run_due():
    now=now_utc()
    with SessionSesiones() as db:
        # A worker crash after claiming never triggers a duplicate send on restart.
        db.query(TestSend).filter(TestSend.estado=='en_proceso',TestSend.programada_en<now-timedelta(hours=1)).update(
            {'estado':'incierta','detalle':'Proceso interrumpido: revisar en Meta; no se reenvía automáticamente'})
        db.commit()
        keys=[r.id for r in db.query(TestSend).filter(TestSend.estado=='programada',TestSend.programada_en<=now).limit(10)]
    for key in keys:
        with SessionSesiones() as db:
            claimed=db.query(TestSend).filter_by(id=key,estado='programada').update({'estado':'en_proceso'})
            db.commit()
            if not claimed:continue
            row=db.get(TestSend,key)
            recipient,name,language,values,expected,due=(row.telefono,row.nombre,row.idioma,json.loads(row.valores_json),row.huella,row.programada_en)
        if now-due>timedelta(hours=1):
            finish(key,'vencida','Se omitió porque pasó más de una hora desde la hora programada');continue
        try:
            allowed_recipient(recipient)
            template=await fetch_template(name,language)
            validate_template(template,values)
            if fingerprint(template)!=expected:raise ValueError('La plantilla cambió después de programarla')
        except Exception:
            finish(key,'bloqueada','Revisar aprobación, contenido, idioma, permisos de Meta y destinatario de prueba');continue
        components=[{'type':'body','parameters':[{'type':'text','text':v} for v in values]}] if values else []
        # No retries: after a timeout the message may already have reached Meta.
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response=await client.post(f'https://graph.facebook.com/v21.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages',
                    headers={'Authorization':'Bearer '+settings.WHATSAPP_TOKEN},json={
                        'messaging_product':'whatsapp','to':recipient,'type':'template',
                        'template':{'name':name,'language':{'code':language},'components':components}})
            if not response.is_success:
                finish(key,'fallida','Meta rechazó el envío (HTTP '+str(response.status_code)+'); no se reintenta');continue
            wamid=response.json().get('messages',[{}])[0].get('id')
            if not wamid:
                finish(key,'incierta','Meta no devolvió identificador; revisar antes de repetir');continue
            finish(key,'aceptada','Meta aceptó el envío; no confirma entrega ni lectura',wamid)
            from app.services.cost_analytics import record_whatsapp_response
            await asyncio.to_thread(record_whatsapp_response,response,recipient,'template')
        except Exception:
            finish(key,'incierta','No se pudo confirmar el envío; revisar en Meta antes de repetir')


def main():
    import argparse
    parser=argparse.ArgumentParser(description='Prueba única programada, solo números del equipo autorizados')
    commands=parser.add_subparsers(dest='action',required=True)
    command=commands.add_parser('programar')
    for name in ('id','telefono','plantilla','idioma','cuando','valores'):
        command.add_argument('--'+name,required=True)
    commands.add_parser('listar')
    commands.add_parser('cancelar').add_argument('--id',required=True)
    args=parser.parse_args()
    try:
        if args.action=='listar':result=list_tests()
        elif args.action=='cancelar':cancel(args.id);result={'id':args.id,'estado':'cancelada'}
        else:
            values=json.loads(args.valores)
            if not isinstance(values,list):raise ValueError('Los valores deben ser una lista JSON')
            result=asyncio.run(schedule(args.id,args.telefono,args.plantilla,args.idioma,values,datetime.fromisoformat(args.cuando)))
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,TypeError) as error:
        parser.exit(2,str(error)+'\n')


if __name__=='__main__':main()
