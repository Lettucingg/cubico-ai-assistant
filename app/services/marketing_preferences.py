"""Persistent WhatsApp marketing suppression, independent of customer accounts."""
import re
import unicodedata
from datetime import datetime
from sqlalchemy import Column, String, DateTime
from sqlalchemy.exc import IntegrityError
from app.db.session_store import BaseSesiones, SessionSesiones, engine_sesiones
from app.services.outbound_templates import normalize_phone


class MarketingSuppression(BaseSesiones):
    __tablename__ = 'marketing_suppressions'
    telefono = Column(String(40), primary_key=True)
    motivo = Column(String(100), nullable=False)
    creada_en = Column(DateTime, nullable=False, default=datetime.utcnow)


MarketingSuppression.__table__.create(engine_sesiones, checkfirst=True)


def requests_optout(text):
    value = ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c))
    value = re.sub(r'[^a-z0-9\s]', ' ', value)
    value = ' '.join(value.split())
    return value in {'baja', 'stop', 'unsubscribe', 'cancelar publicidad', 'no mas publicidad'} or bool(re.search(
        r'\b(?:no (?:me )?(?:envien|manden|envies|mandes) mas (?:mensajes|publicidad|promociones)|'
        r'no quiero (?:recibir )?mas (?:publicidad|promociones)|'
        r'(?:darme|denme|dame) de baja|stop (?:sending me |sending )?(?:messages|promotions))\b', value))


def suppress(phone, reason='Solicitud del destinatario'):
    number = normalize_phone(phone)
    with SessionSesiones() as db:
        db.add(MarketingSuppression(telefono=number, motivo=reason[:100]))
        try:
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            return False


def is_suppressed(phone):
    with SessionSesiones() as db:
        return db.get(MarketingSuppression, normalize_phone(phone)) is not None
