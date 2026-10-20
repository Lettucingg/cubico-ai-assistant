"""Pickup directions come only from an explicitly verified map pin."""
import re
from urllib.parse import urlsplit
from app.core.config import settings


def _map_url(link):
    try:
        url = urlsplit(link)
        host = (url.hostname or '').lower()
        allowed = (host in {'maps.app.goo.gl', 'maps.google.com', 'maps.apple.com'}
                   or host == 'goo.gl' and url.path.startswith('/maps')
                   or host in {'google.com', 'www.google.com'} and url.path.startswith('/maps')
                   or host in {'waze.com', 'www.waze.com'} and url.path.startswith('/ul'))
        return bool(url.scheme == 'https' and not url.username and not url.password and allowed)
    except ValueError:
        return False


def location_config():
    import json
    from app.db.session_store import UbicacionLocal, SessionSesiones
    with SessionSesiones() as db:
        row = db.get(UbicacionLocal, 1)
        if row:
            return json.loads(row.contenido)
    return {'direccion': settings.CUBICO_LOCAL_ADDRESS.strip(),
            'enlace': settings.CUBICO_LOCATION_URL.strip(),
            'confirmada': settings.CUBICO_LOCATION_VERIFIED,
            'latitud': settings.CUBICO_LOCATION_LATITUDE or None,
            'longitud': settings.CUBICO_LOCATION_LONGITUDE or None}


def save_location(data, operator):
    import math
    import json
    from datetime import datetime
    from app.db.session_store import UbicacionLocal, SessionSesiones
    address, link = data['direccion'].strip(), data['enlace'].strip()
    if not address or len(address) > 1000 or not _map_url(link):
        raise ValueError('Escribe la dirección y un enlace HTTPS de Google Maps, Apple Maps o Waze.')
    lat, lon = data.get('latitud'), data.get('longitud')
    if (lat is None) != (lon is None):
        raise ValueError('Completa ambas coordenadas o deja las dos vacías para enviar el enlace.')
    if lat is not None:
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError('Las coordenadas no son válidas.')
    value = {'direccion': address, 'enlace': link, 'latitud': lat, 'longitud': lon,
             'confirmada': data['confirmada'] is True}
    with SessionSesiones() as db:
        row = db.get(UbicacionLocal, 1)
        if row is None:
            row = UbicacionLocal(id=1)
            db.add(row)
        row.contenido = json.dumps(value)
        row.operador = operator
        row.actualizado_en = datetime.utcnow()
        db.commit()
    return value


def verified_location(config=None):
    config = location_config() if config is None else config
    if not config.get('confirmada') or not config.get('direccion') or not _map_url(config.get('enlace', '')):
        return None
    return {'direccion': config['direccion'], 'enlace': config['enlace']}


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


def native_location(config=None):
    """Never infer a pin from an address, a shortened URL or conversation history."""
    import math
    import hashlib
    import json
    config = location_config() if config is None else config
    point = verified_location(config)
    if not point:
        return None
    try:
        latitude = float(config.get("latitud"))
        longitude = float(config.get("longitud"))
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


def location_preview():
    import hashlib
    import json
    config = location_config()
    point = verified_location(config)
    if not point:
        return None
    native = native_location(config)
    if native:
        return {**native, 'tipo': 'location'}
    message = 'Ubicación de Cúbico: ' + point['direccion'] + '\n' + point['enlace']
    return {'tipo': 'enlace', 'ubicacion': {'name': 'Cúbico', 'address': point['direccion']},
            'enlace': point['enlace'], 'revision': hashlib.sha256(message.encode()).hexdigest()}
