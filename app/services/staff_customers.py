"""Authenticated panel-only customer search and configured mailbox formatting.

Never called from the public WhatsApp verification flow. No session verification,
association or business data is written by this module.
"""
import re
import unicodedata
from sqlalchemy import func, select
from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import ClienteCBC, Agencia
from app.tools.clientes import normalizar_codigo_cliente


def plain(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value).lower()) if not unicodedata.combining(c))


def normalized_sql(value):
    for a,b in zip('áéíóúüñÁÉÍÓÚÜÑ','aeiouunAEIOUUN'):
        value=func.replace(value,a,b)
    value=func.lower(value)
    for c in (' ', '-', '.', "'", '(', ')', '+'):
        value=func.replace(value,c,'')
    return value


def compact(value):
    return re.sub(r'[^a-z0-9]', '', plain(value))


def search(query):
    query=' '.join(query.split()).strip()
    if not 3 <= len(query) <= 120:
        raise ValueError('Busca con al menos tres caracteres y un máximo de 120.')
    code=normalizar_codigo_cliente(query)
    digits=re.sub(r'\D','',query)
    is_phone=bool(re.fullmatch(r'[+\d ()-]+',query) and 8 <= len(digits) <= 15)
    tokens=[compact(t) for t in query.split() if len(compact(t))>=2][:6]
    if not tokens:
        raise ValueError('Escribe un nombre, código o teléfono completo.')
    results=[]
    with SessionLocal() as db:
        for model,kind in ((ClienteCBC,'cbc'),(Agencia,'agencia')):
            name=func.coalesce(model.nombre,'')
            if kind=='cbc':
                name=name+' '+func.coalesce(model.apellido,'')
            fields=[model.codigo,model.nombre,model.telefono]
            if kind=='cbc': fields.append(model.apellido)
            statement=select(*fields).where(model.activo.isnot(False))
            if is_phone:
                statement=statement.where(normalized_sql(func.coalesce(model.telefono,''))==digits)
            elif re.fullmatch(r'CBC[-_\s]?\d+',query,re.I):
                statement=statement.where(normalized_sql(model.codigo)==compact(code))
            else:
                # SQL parameters + escaped LIKE prevent %/_ from becoming wildcards.
                statement=statement.where(*[normalized_sql(name).contains(t,autoescape=True) for t in tokens])
            rows=db.execute(statement.order_by(model.codigo).limit(11)).all()
            # Agency codes can be purely alphabetic; exact code lookup takes priority
            # within that identity type but still does not resolve a cross-type collision.
            if not is_phone and not re.fullmatch(r'CBC[-_\s]?\d+',query,re.I):
                exact=db.execute(select(*fields).where(model.activo.isnot(False),func.upper(model.codigo)==code).limit(2)).all()
                if exact: rows=exact
            for row in rows:
                name=(str(row.nombre or '')+' '+str(getattr(row,'apellido','') or '')).strip()
                number=re.sub(r'\D','',str(row.telefono or ''))
                results.append({'codigo':normalizar_codigo_cliente(row.codigo),'tipo':kind,'nombre':name,
                                'telefono_referencia':('…'+number[-4:]) if number else 'Sin teléfono'})
    return {'clientes':results[:10],'detalle_limitado':len(results)>10,'fuente':'Clientes y agencias activos en el sistema de Cúbico.'}


def identity(code,kind):
    if kind not in {'cbc','agencia'}:
        raise ValueError('Selecciona el tipo de cliente de la búsqueda.')
    found=search(normalizar_codigo_cliente(code))
    return next((c for c in found['clientes'] if c['codigo']==normalizar_codigo_cliente(code) and c['tipo']==kind),None)


def reference(question):
    """Extract only explicit references; a name is never inferred from the operator."""
    match=re.search(r'\bCBC[-_\s]?\d+\b',question,re.I)
    if match:return match.group()
    normalized=plain(question)
    if 'tracking' not in normalized and re.search(r'\b(?:telefono|numero|celular)\b',normalized):
        number=re.search(r'(?<!\d)(?:\+?\d[ ()-]*){8,15}(?!\d)',question)
        if number:return number.group().strip()
    match=re.search(r'casillero(?:\s+(?:aereo|aerea|maritimo|maritima))?\s+de(?:l)?\s+(?:cliente\s+)?(.+)',normalized)
    if not match:
        match=re.search(r'(?:cuenta|saldo|facturas?|paquetes?|cliente|direccion)\s+de(?:l)?\s+(.+)',normalized)
    if not match:
        match=re.search(r'\b(?:busca(?:r|me)?|encuentra|localiza)\s+(?:(?:al?\s+)?cliente\s+)?(.+)',normalized)
    if match:
        value=re.split(r'[,;?!\n]|\s+(?:por favor|porfa|para que|y dime|y prepara|por aire|por mar|aereo|maritimo)\b',match.group(1))[0].strip(' .:')
        if value not in {'miami','china','panama','cliente','este cliente','mi cliente','cubico','retiro','local'} and 3<=len(value)<=120:
            return value
    return None


def mailbox(customer,question):
    """Format only configured warehouse fields and the actual active identity."""
    text=plain(question)
    ocean=any(w in text for w in ('maritimo','ocean','por mar'))
    air=any(w in text for w in ('aereo','aerea','por aire'))
    modes=['ocean'] if ocean and not air else ['aereo'] if air and not ocean else ['aereo','ocean']
    code,name=customer['codigo'],customer['nombre']
    sections=[];missing=[]
    for mode in modes:
        label=('China ' if 'china' in text else 'Miami ')+('marítimo' if mode=='ocean' else 'aéreo')
        if 'china' in text:
            if mode=='ocean':
                address=settings.CUBICO_CHINA_OCEAN_ADDRESS.strip();route=settings.CUBICO_CHINA_OCEAN_ROUTE_CODE.strip()
                phones=[p.strip() for p in (settings.CUBICO_CHINA_OCEAN_PHONE_PRIMARY,settings.CUBICO_CHINA_OCEAN_PHONE_SECONDARY) if p.strip()]
                required={'dirección':address,'código de ruta':route,'teléfono':' / '.join(phones)}
                lines=[f'SHIPPING MARK: CUBICO-{code} ({route})',address+' '+route+' (CUBICO-'+code+')','Tel: '+' / '.join(phones)]
            else:
                address=settings.CUBICO_CHINA_AIR_ADDRESS.strip();phone=settings.CUBICO_CHINA_AIR_PHONE.strip()
                required={'dirección':address,'teléfono':phone}
                lines=[f'SHIPPING MARK: CUBICO-{code} AÉREO',address,f'源琪达货运 (CUBICO-{code})','Tel: '+phone]
        else:
            street=settings.CUBICO_MIAMI_STREET.strip();city=settings.CUBICO_MIAMI_CITY_ZIP.strip();phone=settings.CUBICO_MIAMI_PHONE.strip()
            required={'calle':street,'ciudad y código postal':city,'teléfono':phone}
            mark=' OCEAN' if mode=='ocean' else ''
            lines=[f'{name}{mark} {code}',street,f'CUBICO{mark} {code} UNIT2',city,'Tel: '+phone]
        absent=[key for key,value in required.items() if not value]
        if absent:
            missing.append(label+': falta configurar '+', '.join(absent)+'.')
        else:
            sections.append({'modalidad':label,'direccion':'\n'.join(lines)})
    return {'direcciones':sections,'faltantes':missing,'fuente':'Identidad activa del cliente y configuración vigente de bodegas; no es la dirección del local de retiro.'}
