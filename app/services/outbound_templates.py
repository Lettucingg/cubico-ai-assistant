"""Approved first-contact templates: concrete content retained for reply context."""
import hashlib
import json
import re
import httpx
from app.core.config import settings


def normalize_phone(value):
    value=re.sub(r'[ +()\-]','',value.strip())
    if re.fullmatch(r'[2-9][0-9]{7}',value):value='507'+value
    if not re.fullmatch(r'[1-9][0-9]{7,14}',value):
        raise ValueError('Escribe un número internacional válido; en Panamá puedes escribir los ocho dígitos')
    return value


def describe(template):
    if template.get('status')!='APPROVED':return None
    if template.get('category') not in {'UTILITY','MARKETING'}:return None
    body=None;image=False;footer='';buttons=[]
    for component in template.get('components',[]):
        kind=component.get('type')
        if kind=='HEADER' and component.get('format')=='IMAGE' and not image:image=True
        elif kind=='BODY' and body is None:body=component.get('text','')
        elif kind=='FOOTER':footer=component.get('text','')
        elif kind=='BUTTONS':
            for button in component.get('buttons',[]):
                # Fixed URLs are inherited from the approved template on send.
                if button.get('type')!='URL' or '{{' in button.get('url',''):return None
                if not button.get('url','').startswith('https://'):return None
                buttons.append({'texto':button.get('text',''),'url':button['url']})
        else:return None
    if not body:return None
    variables=set(re.findall(r'{{(.*?)}}',body))
    if variables!={str(i+1) for i in range(len(variables))} or len(variables)>5:return None
    row={'nombre':template['name'],'idioma':template['language'],'categoria':template['category'],
         'texto':body,'pie':footer,'imagen':image,'botones':buttons,'variables':len(variables)}
    row['huella']=hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return row


async def list_templates():
    account=settings.WHATSAPP_BUSINESS_ACCOUNT_ID.strip()
    if not re.fullmatch(r'[0-9]+',account):raise ValueError('Falta configurar la cuenta de WhatsApp Business en el servidor')
    rows=[];after=None
    async with httpx.AsyncClient(timeout=15) as client:
        for _ in range(10):
            params={'fields':'name,language,status,category,components','limit':100}
            if after:params['after']=after
            response=await client.get(f'https://graph.facebook.com/v21.0/{account}/message_templates',
                headers={'Authorization':'Bearer '+settings.WHATSAPP_TOKEN},params=params)
            if not response.is_success:raise ValueError('No se pudieron consultar las plantillas de Meta; revisa permisos y conexión')
            data=response.json()
            for template in data.get('data',[]):
                row=describe(template)
                if row:rows.append(row)
            paging=data.get('paging',{})
            if not paging.get('next'):return sorted(rows,key=lambda r:(r['nombre'],r['idioma']))
            after=paging.get('cursors',{}).get('after')
            if not after:break
    raise ValueError('No se pudo completar la lista de plantillas; no se muestran resultados incompletos')


def render(row,values):
    if len(values)!=row['variables'] or any(not isinstance(v,str) or not v.strip() or len(v)>300 for v in values):
        raise ValueError('Completa todas las variables de la plantilla, con un máximo de 300 caracteres cada una')
    text=re.sub(r'{{([0-9]+)}}',lambda match:values[int(match[1])-1].strip(),row['texto'])
    parts=[text,row['pie']]+[button['texto']+': '+button['url'] for button in row['botones']]
    return '\n\n'.join(part for part in parts if part)


def ai_context(row,text):
    return ('El equipo inició el contacto con esta plantilla de WhatsApp: '+row['nombre']+' ('+row['idioma']+'). '
            'El contenido siguiente explica por qué podría responder la persona; no es una verificación de identidad, '
            'una cuenta creada ni una tarifa asignada. Respeta el estado de entrega. Si responde sobre esta invitación, '
            'continúa ese tema sin preguntar de nuevo en qué puedes ayudar. Consulta fuentes vigentes para elegibilidad y datos privados. '
            'No inventes un registro completado ni una promoción distinta.\nContenido enviado:\n'+text)
