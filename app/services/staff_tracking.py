"""Public tracking evidence for the private panel assistant, without account access."""
import re
from datetime import datetime, timezone
from app.tools.ptyfreight import consultar_tracking


def extract_trackings(text):
    # Never send URLs, paths, emails or invoice/customer identifiers to the lookup.
    text = re.sub(r'https?://\S+|\S+@\S+', ' ', text)
    found = []
    for match in re.finditer(r'(?<![\w/-])([A-Za-z0-9]{6,40})(?![\w/-])', text):
        value = match.group(1)
        if re.match(r'(?:CBC|FAC|OP)\d', value, re.I):
            continue
        if not re.search(r'\d', value):
            continue
        if value.isdigit() and len(value) < 10:
            continue
        if value not in found:
            found.append(value)
    return found


def lookup(session, numbers, mode):
    now = datetime.now(timezone.utc).isoformat()
    if len(numbers) > 3:
        return {'telefono': session.telefono, 'codigo_cliente': None, 'consultado_en': now,
                'respuesta': 'Pega hasta tres trackings por consulta para revisar cada resultado con claridad.',
                'borrador': '', 'datos': {'trackings': []}, 'alcance': 'tracking_publico', 'privado': True}
    evidence, lines = [], []
    for number in numbers:
        try:
            raw = consultar_tracking(number)
        except Exception:
            raw = {'error': True}
        if not isinstance(raw, dict) or raw.get('error') or not isinstance(raw.get('encontrado'), bool):
            status = 'No pude consultar el estado en este momento. Esto no significa que el paquete no esté registrado.'
            available, found = False, False
        elif not raw['encontrado']:
            status = 'No aparece registrado en la consulta. Es posible que aún no haya llegado a nuestras bodegas; no puedo confirmar esa causa.'
            available, found = True, False
        else:
            available, found = True, True
            state = str(raw.get('estado') or '').lower().replace('_', ' ')
            if state in {'en transito', 'en tránsito'}:
                status = 'El último registro indica en tránsito. La ubicación exacta y la fecha de entrega requieren confirmación.'
            elif state in {'en miami', 'recibido en miami'}:
                status = 'El último registro disponible indica recibido en Miami. No confirma una llegada posterior a Panamá.'
            elif state in {'en panama', 'en panamá', 'recibido en panama', 'recibido en panamá'}:
                status = 'El último registro indica Panamá. Esto no confirma disponibilidad para retirar en nuestro local ni entrega al cliente.'
            else:
                status = 'El tracking aparece registrado. Necesitamos confirmar la ubicación actual y si está habilitado para retiro o entrega.'
            if raw.get('identificacion_incorrecta') is True:
                status += ' Advertencia: aparece mal identificado; el equipo debe revisar y corregir su identificación.'
        # Do not expose warehouse/provider internals, customer details or billing.
        evidence.append({'tracking': number, 'disponible': available, 'encontrado': found,
                         'estado_publico': status, 'consultado_en': now})
        lines.append(number + ': ' + status)
    answer = '\n\n'.join(lines)
    return {'telefono': session.telefono, 'codigo_cliente': None, 'consultado_en': now,
            'respuesta': answer + '\n\nConsulta pública: no verifica a quién pertenece el paquete, saldos ni autorización de retiro. El servicio puede reutilizar un resultado de hasta tres minutos.',
            'borrador': answer if mode == 'borrador' else '',
            'datos': {'trackings': evidence}, 'alcance': 'tracking_publico', 'privado': True}
