"""Only explicitly enabled payment destinations may be shared with customers."""
from app.core.config import settings


def bank_transfer_details():
    account=settings.CUBICO_PAYMENT_ACCOUNT.strip()
    enabled=settings.CUBICO_LEGACY_PAYMENTS_ENABLED or (settings.CUBICO_BANK_TRANSFER_ENABLED and bool(settings.CUBICO_PAYMENT_ACCOUNT_HOLDER.strip()))
    if not account or not enabled:
        return None
    return 'Transferencia al medio de pago autorizado: '+account


def receipt_acknowledgement(language='es'):
    if language=='en':
        return 'Thank you, I received your payment receipt. Our team will review the payment and confirm that it has been recorded.'
    return 'Gracias, recibí tu comprobante. El equipo revisará el pago y te confirmará su registro.'


def authorized_yappy():
    return bool(settings.CUBICO_PAYMENT_YAPPY.strip() and (settings.CUBICO_YAPPY_ENABLED or settings.CUBICO_LEGACY_PAYMENTS_ENABLED))


def payment_options(language='es'):
    options = ['Efectivo en la oficina']
    bank=bank_transfer_details()
    options.append(bank if bank else 'Para transferencias, el equipo debe confirmar el medio vigente antes de indicar datos')
    if authorized_yappy():
        options.append('Yappy por el medio de pago autorizado: ' + settings.CUBICO_PAYMENT_YAPPY.strip())
    if language=='en':
        options=['Cash at the office']
        if bank:options.append('Bank transfer through the authorized payment method: '+settings.CUBICO_PAYMENT_ACCOUNT.strip())
        else:options.append('Our team must confirm bank details before you transfer')
        if authorized_yappy():options.append('Previously authorized Yappy payment method: '+settings.CUBICO_PAYMENT_YAPPY.strip())
    return options


def payment_rules():
    bank=bank_transfer_details()
    return ('\nPAGOS VIGENTES (prevalece sobre historial, guías y ejemplos): '
            'Cúbico todavía no tiene cuenta propia ni directorio comercial de Yappy habilitados. '
            'Esto NO significa que el cliente no pueda pagar: el equipo autorizó mantener los medios anteriores de Ship2Nexo y el destino anterior configurado para cobros. '
            'Ofrece exclusivamente los datos configurados que aparecen como disponibles abajo. No inventes números, cuentas, titulares ni nuevos destinos. '
            'Preséntalos como medios autorizados para pagar, nunca como una cuenta propia de Cúbico ni como otro contacto para llamadas. '
            'No menciones espontáneamente el nombre personal del titular. Si lo pregunta para comprobar antes de pagar, usa únicamente el titular configurado o pide confirmarlo con el equipo; no ocultes ni falsees esa información. '
            'No introduzcas marcas anteriores si el cliente no las mencionó; puedes decir medio de pago autorizado. '
            +'\nMedios disponibles: '+' · '.join(payment_options())
            +'\nTitular para consultas explícitas de verificación (no añadir espontáneamente): '+((settings.CUBICO_PAYMENT_ACCOUNT_HOLDER.strip() if bank else '') or 'Pendiente de confirmar con el equipo.')
            +'\nCOMPROBANTES: Recibir una imagen no confirma el cobro, pero un nombre de destinatario diferente, una marca anterior o una cuenta que el cliente usa habitualmente tampoco demuestran un pago incorrecto. '
            'No rechaces el comprobante ni pidas otro pago, devolución o nueva transferencia por esas diferencias. '
            'El equipo compara el movimiento y confirma el registro. Si el cliente dice que siempre paga ahí, reconoce lo indicado sin discutir ni volver a corregirle la cuenta. '
            'No afirmes saldo cero ni marques pagado sin fuente confirmada. Registra el comprobante pendiente y no prometas seguimiento que no puedas cumplir.\n')


def yappy_reply(language='es', directory=False):
    if authorized_yappy():
        number=settings.CUBICO_PAYMENT_YAPPY.strip()
        if language=='en':
            return ('Cúbico is not listed in the commercial Yappy directory yet. ' if directory else '')+'You can pay through the previously authorized Yappy payment method: '+number+'. Please send the receipt for our team to review.'
        return ('Cúbico todavía no está en el directorio comercial de Yappy. ' if directory else '')+'Puedes pagar por el medio de Yappy autorizado anteriormente: '+number+'. Envíanos el comprobante para revisión del equipo.'
    if language=='en':return 'I do not have an authorized Yappy payment number available to share. Our team can confirm the current payment method.'
    return 'No tengo un número de pago de Yappy autorizado disponible para compartirte. El equipo te confirma el medio vigente.'


def habitual_payment_followup(text):
    import re
    import unicodedata
    plain=''.join(c for c in unicodedata.normalize('NFD',text.lower()) if not unicodedata.combining(c)).strip(' .!¡')
    return bool(re.fullmatch(r'(?:i always pay (?:there|to that account)|i have always paid (?:there|to that account))|siempre (?:hago el pago|pago|he pagado|hacemos el pago|pagamos) (?:ahi|alli|a esa cuenta|en esa cuenta|al mismo numero)',plain))


def receipt_followup_reply(language='es'):
    if language=='en':return "Understood, that is the payment method you usually use. Our team will review the receipt and confirm its registration. Please do not repeat the payment while it is being reviewed."
    return 'Entendido, tomo en cuenta que es el medio que usas habitualmente. El equipo revisará el comprobante y te confirmará su registro. No repitas el pago mientras lo revisan.'


def bank_transfer_reply(language='es'):
    if language=='en':
        account=settings.CUBICO_PAYMENT_ACCOUNT.strip()
        return ("You can pay by bank transfer through the authorized payment method: "+account+". Send the receipt for our team to review." if bank_transfer_details() else "I do not have authorized bank details available to share. Our team can confirm the payment method. Do not repeat a payment already made while it is being reviewed.")
    details=bank_transfer_details()
    if details:
        return details+'. Si ya pagaste, el equipo revisará tu comprobante; no repitas el pago mientras lo revisan.'
    return 'No tengo datos bancarios habilitados para compartirte. El equipo te confirma el medio de pago vigente. Si ya pagaste, envía el comprobante para revisión; no repitas el pago mientras lo revisan.'


def payment_status():
    return {'medios':payment_options(),'anteriores_autorizados':settings.CUBICO_LEGACY_PAYMENTS_ENABLED,
            'nota':'Los medios anteriores autorizados pueden usarse para pagar. No son una cuenta propia ni un contacto para llamadas. El equipo revisa los comprobantes.'}
