"""Pickup directions come only from an explicitly verified map pin."""
import re
from urllib.parse import urlsplit
from app.core.config import settings


def verified_location():
    if not settings.CUBICO_LOCATION_VERIFIED:
        return None
    address=settings.CUBICO_LOCAL_ADDRESS.strip()
    link=settings.CUBICO_LOCATION_URL.strip()
    try:
        url=urlsplit(link)
        host=(url.hostname or '').lower()
        allowed=(host in {'maps.app.goo.gl','maps.google.com','maps.apple.com'}
                 or host=='goo.gl' and url.path.startswith('/maps')
                 or host in {'google.com','www.google.com'} and url.path.startswith('/maps')
                 or host in {'waze.com','www.waze.com'} and url.path.startswith('/ul'))
        if url.scheme!='https' or url.username or url.password or not allowed or not address:
            return None
    except ValueError:
        return None
    return {'direccion':address,'enlace':link}


def location_question(text, history=None):
    text=text.lower().strip()
    # Warehouse/shipping addresses are separate from local customer pickup.
    if re.search(r'\b(miami|china|casillero|shipping mark)\b',text): return False
    if re.search(r'paquete|pedido|tracking|carga|env[ií]o',text) and not re.search(r'local|oficina|retir|sucursal|ustedes',text): return False
    direct=re.search(r'ubicaci[oó]n|\b(?:d[oó]nde|qu[eé] lugar)\s+(?:es|est[aá]n|queda|est[aá])\b|direcci[oó]n\s+(?:del?\s+)?(?:local|oficina)|\b(?:momi|mimis?|momis)\b',text)
    if direct: return True
    # A short follow-up is location-related only when the customer has raised it recently.
    if re.search(r'^\??$|\bestoy\s+(?:aqu[ií]|en\s+el\s+dorado|cerca|serca)|\ba un costado\b|\bal lado\b',text):
        for msg in (history or [])[-8:]:
            if msg.get('role')=='user' and re.search(r'ubicaci[oó]n|\bd[oó]nde\b|qu[eé] lugar|momi',str(msg.get('content','')).lower()):
                return True
    return False


def location_rules():
    point=verified_location()
    if point:
        return ('UBICACIÓN DE RETIRO CONFIRMADA POR EL EQUIPO:\nDirección: '+point['direccion']+'\nPin exacto: '+point['enlace']+
                '\nComparte este pin cuando pidan ubicación. No inventes referencias, distancias, rutas, fachadas o negocios vecinos. No confirmes que una foto corresponde al local ni que el cliente ya llegó sin verificación del equipo. Si hay dudas o una indicación del equipo de que ese local cerró, escala antes de mandarlo allí.')
    return ('UBICACIÓN DE RETIRO NO VERIFICADA: no hay un pin vigente confirmado. No uses direcciones antiguas, el historial, imágenes ni sugerencias del cliente para indicar dónde retirar. Nunca confirmes cercanía a El Dorado, Momi u otra referencia, ni digas que entre, pase o que ya llegó al local. Ante una consulta de ubicación, escala al equipo para confirmar el punto exacto. No inventes una dirección ni un enlace. Esto no afecta las direcciones de recepción de carga en Miami y China.')


def native_location():
    """Never infer a pin from an address, a shortened URL or conversation history."""
    import math
    import hashlib
    import json
    point = verified_location()
    if not point:
        return None
    try:
        latitude = float(settings.CUBICO_LOCATION_LATITUDE)
        longitude = float(settings.CUBICO_LOCATION_LONGITUDE)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(latitude) and math.isfinite(longitude)
            and -90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    location = {'latitude': latitude, 'longitude': longitude,
                'name': 'Cúbico', 'address': point['direccion']}
    if len(location['address']) > 1000:
        return None
    # The preview and WhatsApp use precisely the same coordinates.
    link = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
    revision = hashlib.sha256(json.dumps(location, sort_keys=True).encode()).hexdigest()
    return {'ubicacion': location, 'enlace': link, 'revision': revision}
