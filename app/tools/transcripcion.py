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


def transcribir_audio(audio_bytes: bytes) -> str:
    """
    Envía el audio a Whisper (OpenAI) y devuelve el texto transcrito.
    """
    archivo_audio = ("nota_de_voz.ogg", audio_bytes, "audio/ogg")

    transcripcion = cliente_openai.audio.transcriptions.create(
        model="whisper-1",
        file=archivo_audio,
        language="es",
    )

    return transcripcion.text


async def procesar_nota_de_voz(media_id: str) -> str:
    """
    Función principal: descarga y transcribe una nota de voz de
    WhatsApp, devolviendo el texto listo para pasarle a Claude.
    """
    audio_bytes = await descargar_audio_de_whatsapp(media_id)
    texto = transcribir_audio(audio_bytes)
    return texto