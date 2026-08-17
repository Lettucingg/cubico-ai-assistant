from anthropic import Anthropic

from app.core.config import settings

# El cliente de Anthropic se crea UNA sola vez, igual que hicimos
# con el "engine" de la base de datos. Se reutiliza en cada llamada,
# en vez de crear una conexión nueva cada vez.
cliente_claude = Anthropic(api_key=settings.ANTHROPIC_API_KEY)


SYSTEM_PROMPT = """
Eres el asistente virtual de Cúbico, una empresa de courier en Panamá
que trae paquetes desde Miami. Tu trabajo es ayudar a los clientes
con sus preguntas de forma amable, clara y profesional.

Por ahora estás en una fase temprana de desarrollo: aún no tienes
acceso a la base de datos de paquetes ni facturas reales. Si el
cliente pregunta algo que requeriría esos datos, explícale
honestamente que todavía no puedes consultar esa información, sin
inventar ningún dato.
"""


def generar_respuesta(texto_cliente: str) -> str:
    """
    Envía el mensaje del cliente a Claude y devuelve el texto de
    la respuesta generada.

    Esta es la versión más simple posible: un solo mensaje, sin
    historial de conversación previo, sin herramientas. Es la base
    sobre la que vamos a construir el resto de la inteligencia del
    bot (contexto, herramientas de negocio, etc.).
    """
    respuesta = cliente_claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": texto_cliente}
        ],
    )

    # La respuesta de Claude viene en una lista de "bloques de
    # contenido" (puede incluir texto, uso de herramientas, etc.).
    # Por ahora, solo nos interesa el texto del primer bloque.
    return respuesta.content[0].text