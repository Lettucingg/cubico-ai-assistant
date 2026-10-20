"""Only publish a voice contact explicitly verified by the business."""
import re
import unicodedata
from app.core.config import settings


def _plain(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text).lower())
                   if not unicodedata.combining(c))


def verified_call_phone():
    phone = settings.CUBICO_HUMAN_CALL_PHONE.strip()
    digits = re.sub(r'\D', '', phone)
    if not settings.CUBICO_HUMAN_CALL_VERIFIED or not re.fullmatch(r'\+?[\d ()-]+', phone):
        return None
    return phone if 8 <= len(digits) <= 15 else None


def call_request(text, history=None):
    plain = _plain(text)
    direct = bool(re.search(r'\b(?:llamar(?:les|los|te|me|nos)?|llamada[s]?|llamen(?:me)?|llamas|llamame|llamenos)\b', plain))
    if direct:
        return True
    # Interpret a failed-number follow-up only when the recent exchange was
    # about calls, not a failed tracking or map link.
    failed_number = ('numero' in plain and any(x in plain for x in ('no funciona', 'no es correcto', 'incorrecto', 'no existe')))
    return failed_number and any(call_request(m.get('content', '')) for m in (history or [])[-6:])


def contact_rules():
    phone = verified_call_phone()
    return ("\nCONTACTO POR LLAMADAS: El número de este chat, el teléfono general del local, "
            "Yappy y los teléfonos de bodegas no acreditan atención humana por voz. "
            "No los ofrezcas para llamar ni confirmar la identidad de la empresa. "
            "No inventes disponibilidad, horarios de llamadas, transferencia ni devolución de llamada. "
            "No prometas que alguien llamará o ya habló con el cliente sin confirmación. "
            "Si solicita una persona, ofrece revisión del equipo por este chat y registra la solicitud "
            "con escalar_a_humano cuando estés atendiendo; en modo borrador no afirmes haberla registrado. "
            + (f"Único número confirmado para llamadas humanas: {phone}."
               if phone else "No hay un número confirmado para llamadas humanas; dilo claramente, sin ofrecer un teléfono alternativo."))


def call_reply():
    phone = verified_call_phone()
    if phone:
        return f"El número confirmado para atención por llamada es {phone}."
    return ("Por este canal te atiendo por chat. No tengo un número confirmado para que llames y te atienda una persona. "
            "Dejé tu solicitud al equipo para que revise lo pendiente contigo por aquí.")
