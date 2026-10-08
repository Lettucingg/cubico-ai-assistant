import asyncio
import math
import json
from decimal import Decimal
from time import perf_counter
from app.services.cost_analytics import record_event, PRICING_DATE
import httpx
from openai import OpenAI

from app.core.config import settings

cliente_openai = OpenAI(api_key=settings.OPENAI_API_KEY)


async def descargar_audio_de_whatsapp(media_id: str) -> bytes:
    """
    Descarga el archivo de audio real desde los servidores de Meta.

    Meta no manda el audio directamente en el webhook — solo un
    "media_id". Hay que hacer dos pasos: primero pedirle a Meta la
    URL real de descarga, y luego descargar el archivo desde ahí.
    """
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        respuesta_info = await client.get(
            f"https://graph.facebook.com/v21.0/{media_id}",
            headers=headers,
        )
        url_descarga = respuesta_info.json()["url"]

        respuesta_audio = await client.get(url_descarga, headers=headers)
        return respuesta_audio.content


def transcribir_audio(audio_bytes: bytes, telefono: str = '') -> str:
    """
    Envía el audio a Whisper (OpenAI) y devuelve el texto transcrito.
    """
    archivo_audio = ("nota_de_voz.ogg", audio_bytes, "audio/ogg")

    inicio = perf_counter()
    try:
        transcripcion = cliente_openai.audio.transcriptions.create(
            model="whisper-1", file=archivo_audio, language="es", response_format="verbose_json",
        )
    except Exception:
        record_event(provider='openai', model='whisper-1', task='transcripcion_audio', phone=telefono, status='error')
        raise
    duration = getattr(transcripcion, 'duration', None)
    seconds = float(duration) if isinstance(duration, (int, float)) and math.isfinite(duration) and duration >= 0 else None
    # Estimate from reported duration. Provider invoice remains authoritative.
    cost = Decimal(str(seconds)) * Decimal('.006') / 60 if seconds is not None else None
    record_event(provider='openai', model='whisper-1', task='transcripcion_audio', phone=telefono,
        audio_seconds=seconds, cost=cost, elapsed_ms=int((perf_counter()-inicio)*1000),
        pricing_json=json.dumps({'usd_per_minute': '.006', 'verified_at': PRICING_DATE,
            'source': 'https://developers.openai.com/api/docs/models/whisper-1'}))
    return transcripcion.text


async def procesar_nota_de_voz(media_id: str, telefono: str = '') -> str:
    """
    Función principal: descarga y transcribe una nota de voz de
    WhatsApp, devolviendo el texto listo para pasarle a Claude.
    """
    audio_bytes = await descargar_audio_de_whatsapp(media_id)
    texto = await asyncio.to_thread(transcribir_audio, audio_bytes, telefono)
    return texto