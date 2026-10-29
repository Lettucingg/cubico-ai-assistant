"""Payment availability is explicit; an old number is not activation."""
from app.core.config import settings


def payment_options():
    options = ['Efectivo en la oficina']
    account = settings.CUBICO_PAYMENT_ACCOUNT.strip()
    options.append('Transferencia ACH: ' + account if account else 'Transferencia ACH; el equipo confirma los datos de la cuenta')
    if settings.CUBICO_YAPPY_ENABLED and settings.CUBICO_PAYMENT_YAPPY.strip():
        options.append('Yappy: ' + settings.CUBICO_PAYMENT_YAPPY.strip())
    return options


def payment_rules():
    state = ('Yappy habilitado únicamente con los datos configurados.'
             if settings.CUBICO_YAPPY_ENABLED and settings.CUBICO_PAYMENT_YAPPY.strip()
             else 'Cúbico NO acepta Yappy actualmente. Está pendiente la asociación del sistema. No ofrezcas números personales, directorio ni fecha de activación. Si preguntan, explica que estará disponible próximamente, sin prometer fecha.')
    return '\nPAGOS VIGENTES (prevalece sobre historial y ejemplos): ' + state + '\nMedios disponibles: ' + ' · '.join(payment_options()) + '. No confirmes un pago solo por un comprobante.\n'


def yappy_reply():
    if settings.CUBICO_YAPPY_ENABLED and settings.CUBICO_PAYMENT_YAPPY.strip():
        return 'Los datos habilitados de Yappy son: ' + settings.CUBICO_PAYMENT_YAPPY.strip() + '. El equipo puede confirmar el destinatario; no implica aparecer en el directorio.'
    return 'Por ahora Cúbico no acepta Yappy. Estará disponible próximamente, sin fecha confirmada. Puedes pagar por transferencia ACH o en efectivo en la oficina.'
