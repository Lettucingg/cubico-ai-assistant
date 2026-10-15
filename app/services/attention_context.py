"""Guía interna basada en hechos del historial; no consulta ni modifica cuentas."""
import unicodedata


def _plain(value, limit=1600):
    return str(value or '').strip()[:limit]


def attention_context(reason, history, active=True):
    if not active:
        return None
    reason = _plain(reason)
    key = ''.join(c for c in unicodedata.normalize('NFD', reason.lower()) if not unicodedata.combining(c))
    category = 'Revisión del equipo'
    steps = ['Leer el historial y confirmar qué solicitud sigue pendiente.',
             'Consultar los datos vigentes antes de confirmar una solución al cliente.']
    draft = 'Voy a revisar tu solicitud para darte una respuesta precisa. ¿Qué necesitas confirmar en este momento?'
    if 'mal identificado' in key or 'malid' in key:
        category = 'Paquete mal identificado'
        steps = ['Localizar el tracking indicado y revisar la identificación del destinatario.',
                 'Confirmar el código del cliente y gestionar la corrección con bodega.',
                 'Comprobar que la corrección quedó registrada antes de avisar que está resuelto.']
        draft = 'El registro de tu paquete requiere una revisión de identificación. Necesitamos confirmar a quién corresponde antes de indicarte cómo continuar.'
    elif 'miami' in key and any(w in key for w in ['demora', 'dias', 'retraso']):
        category = 'Demora en Miami'
        steps = ['Consultar de nuevo el tracking y la fecha de su último movimiento.',
                 'Confirmar con operaciones si salió de Miami o llegó a Panamá.',
                 'Dar una fecha de entrega solo si está confirmada.']
        draft = 'El último registro disponible indica Miami. Necesitamos confirmar con operaciones si hay movimientos posteriores antes de darte una fecha de llegada.'
    elif any(w in key for w in ['ubicacion', 'direccion del local', 'pin vigente']):
        category = 'Ubicación por confirmar'
        steps = ['Confirmar con el responsable la dirección y el enlace de mapas vigentes.',
                 'Compartir únicamente el punto confirmado; no validar referencias de locales anteriores.']
        draft = 'Para orientarte bien, necesito confirmar el punto exacto de retiro. Evitemos que vayas a una dirección anterior.'
    elif any(w in key for w in ['tracking', 'rastreo']):
        category = 'Consulta de tracking pendiente'
        steps = ['Repetir la consulta del tracking indicado y revisar el resultado real.',
                 'Distinguir una falla de consulta de un paquete no registrado.',
                 'Si no está registrado, indicarlo sin afirmar una ubicación ni una llegada.']
        draft = 'Necesito verificar el estado actualizado de ese tracking antes de confirmarte dónde está. Si no aparece registrado, te lo indicaré claramente.'
    elif any(w in key for w in ['pago', 'comprobante', 'factura', 'saldo']):
        category = 'Revisión de pago o facturación'
        steps = ['Revisar todas las facturas pendientes y los abonos registrados del cliente.',
                 'Comparar el comprobante con el movimiento recibido y su referencia.',
                 'Confirmar el saldo real; una notificación individual no representa necesariamente la deuda total.']
        draft = 'Voy a comprobar tus facturas y los pagos registrados para confirmarte el saldo correcto.'
    elif any(w in key for w in ['limite', 'intentos', 'verific', 'identidad']):
        category = 'Verificación pendiente'
        steps = ['Revisar qué dato de verificación falta o no coincide.',
                 'Ayudar al cliente a completar la verificación sin revelar datos privados previamente.']
        draft = 'Vamos a revisar la verificación para que puedas continuar. ¿Puedes confirmarme tu código de cliente y el correo registrado?'
    def latest(roles):
        m = next((m for m in reversed(history or []) if m.get('role') in roles), None)
        if not m:
            return None
        return {'texto': _plain(m.get('content')), 'fecha': m.get('timestamp'),
                'autor': _plain(m.get('autor_tipo') or m.get('role'), 60),
                'estado_entrega': _plain(m.get('estado_entrega'), 60)}
    return {'categoria': category,
            'motivo': reason or 'No se registró un motivo específico. Revisar el historial antes de actuar.',
            'ultimo_cliente': latest({'user'}),
            'ultima_respuesta': latest({'assistant', 'humano'}),
            'pasos': steps, 'borrador': draft,
            'nota': 'Guía interna orientativa. Los mensajes son los últimos del chat, no necesariamente los que originaron la alerta. Revisa si el equipo ya intervino. El borrador no se envía automáticamente ni confirma una gestión realizada.'}
