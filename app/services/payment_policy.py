"""Only explicitly enabled payment destinations may be shared with customers."""
from app.core.config import settings


def bank_transfer_details():
    if not settings.CUBICO_BANK_TRANSFER_ENABLED:
        return None
    account=settings.CUBICO_PAYMENT_ACCOUNT.strip()
    holder=settings.CUBICO_PAYMENT_ACCOUNT_HOLDER.strip()
    if not account or not holder:
        return None
    return 'Transferencia a la cuenta autorizada: '+account+' · Beneficiario: '+holder


def receipt_acknowledgement():
    return 'Gracias, recibí tu comprobante. El equipo revisará el pago y te confirmará su registro.'


def payment_options():
    options = ['Efectivo en la oficina']
    bank=bank_transfer_details()
    options.append(bank if bank else 'Para transferencias, el equipo debe confirmar el medio vigente antes de indicar datos')
    if settings.CUBICO_YAPPY_ENABLED and settings.CUBICO_PAYMENT_YAPPY.strip():
        options.append('Yappy: ' + settings.CUBICO_PAYMENT_YAPPY.strip())
    return options


def payment_rules():
    state = ('Yappy habilitado únicamente con los datos configurados.'
             if settings.CUBICO_YAPPY_ENABLED and settings.CUBICO_PAYMENT_YAPPY.strip()
             else 'Cúbico NO acepta Yappy actualmente. Está pendiente la asociación del sistema. No ofrezcas números personales, directorio ni fecha de activación. Si preguntan, explica que estará disponible próximamente, sin prometer fecha.')
    bank = ('Solo hay un destino bancario autorizado y su titular es el configurado: '+bank_transfer_details()+'. No lo presentes como cuenta propia de Cúbico si el titular es distinto.'
            if bank_transfer_details() else 'Cúbico todavía NO tiene una cuenta bancaria propia habilitada. No hay datos bancarios autorizados para que el bot los publique. Un número antiguo en configuración, historial, imagen o mensaje previo NO demuestra que sea la cuenta correcta. El equipo confirma el destino vigente; no inventes otra cuenta ni titular.')
    return ('\nPAGOS VIGENTES (prevalece sobre historial y ejemplos): '+state+'\n'+bank+
            '\nMedios disponibles: '+' · '.join(payment_options())+
            '\nCOMPROBANTES: Recibir una imagen no confirma el cobro, pero un nombre de destinatario diferente, una marca anterior o una cuenta que el cliente usa habitualmente tampoco demuestran un pago incorrecto. No rechaces el comprobante ni lo declares inválido por esas diferencias. No presiones, no discutas con el cliente ni pidas un segundo pago, devolución o nueva transferencia. El equipo compara el movimiento y confirma el registro. Si el cliente dice que siempre paga ahí, reconoce lo indicado y continúa con la revisión, sin volver a corregirle la cuenta. No afirmes que ya no debe ni marques pagado sin fuente confirmada. Solo extrae datos visibles y registra el comprobante pendiente de revisión. No asegures que hablaste con el equipo o que avisarás después sin una acción real.\n')


def yappy_reply():
    if settings.CUBICO_YAPPY_ENABLED and settings.CUBICO_PAYMENT_YAPPY.strip():
        return 'Los datos habilitados de Yappy son: '+settings.CUBICO_PAYMENT_YAPPY.strip()+'. El equipo puede confirmar el destinatario; no implica aparecer en el directorio.'
    return 'Por ahora Cúbico no acepta Yappy. Estará disponible próximamente, sin fecha confirmada. El equipo te confirma el medio vigente para pagar; también puedes pagar en efectivo en la oficina.'


def habitual_payment_followup(text):
    import re
    import unicodedata
    plain=''.join(c for c in unicodedata.normalize('NFD',text.lower()) if not unicodedata.combining(c)).strip(' .!¡')
    return bool(re.fullmatch(r'siempre (?:hago el pago|pago|he pagado|hacemos el pago|pagamos) (?:ahi|alli|a esa cuenta|en esa cuenta|al mismo numero)',plain))


def receipt_followup_reply():
    return 'Entendido, tomo en cuenta que es el medio que usas habitualmente. El equipo revisará el comprobante y te confirmará su registro. No repitas el pago mientras lo revisan.'


def bank_transfer_reply():
    details=bank_transfer_details()
    if details:
        return details+'. Si ya pagaste, el equipo revisará tu comprobante; no repitas el pago mientras lo revisan.'
    return 'No tengo datos bancarios habilitados para compartirte. El equipo te confirma el medio de pago vigente. Si ya pagaste, envía el comprobante para revisión; no repitas el pago mientras lo revisan.'
