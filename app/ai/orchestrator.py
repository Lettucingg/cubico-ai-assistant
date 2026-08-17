from anthropic import Anthropic

from app.core.config import settings
from app.tools.paquetes import consultar_paquetes_por_codigo

cliente_claude = Anthropic(api_key=settings.ANTHROPIC_API_KEY)


SYSTEM_PROMPT = """
Eres el asistente virtual de Cúbico, una empresa de courier en Panamá
que trae paquetes desde Miami. Tu trabajo es ayudar a los clientes
con sus preguntas de forma amable, clara y profesional.

Reglas importantes:
- NUNCA inventes información de paquetes, facturas o datos del
  cliente. Si necesitas ese tipo de información, usa la herramienta
  disponible para consultarla en la base de datos real.
- Si el cliente pregunta por sus paquetes, pídele su código de
  cliente CBC (ej: "CBC-0001") si aún no lo ha dado.
- Si la herramienta indica que no se encontró el cliente, dile
  amablemente que verifique el código, sin inventar datos.
"""

HERRAMIENTAS = [
    {
        "name": "consultar_paquetes_por_codigo",
        "description": (
            "Busca los paquetes de un cliente usando su código CBC. "
            "Úsala cuando el cliente pregunte por el estado de sus "
            "paquetes, tracking, o cuántos paquetes tiene."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "codigo_cliente": {
                    "type": "string",
                    "description": "El código CBC del cliente, ej: CBC-0001",
                }
            },
            "required": ["codigo_cliente"],
        },
    }
]

FUNCIONES_DISPONIBLES = {
    "consultar_paquetes_por_codigo": consultar_paquetes_por_codigo,
}


def generar_respuesta(texto_cliente: str) -> str:
    """
    Envía el mensaje del cliente a Claude. Si Claude decide usar una
    herramienta, la ejecutamos y le devolvemos el resultado, hasta
    que Claude entregue una respuesta final en texto.
    """
    mensajes = [{"role": "user", "content": texto_cliente}]

    while True:
        respuesta = cliente_claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=500,
            system=SYSTEM_PROMPT,
            tools=HERRAMIENTAS,
            messages=mensajes,
        )

        if respuesta.stop_reason != "tool_use":
            return respuesta.content[0].text

        mensajes.append({"role": "assistant", "content": respuesta.content})

        resultados_de_herramientas = []
        for bloque in respuesta.content:
            if bloque.type == "tool_use":
                nombre_funcion = bloque.name
                parametros = bloque.input

                funcion = FUNCIONES_DISPONIBLES[nombre_funcion]
                resultado = funcion(**parametros)

                resultados_de_herramientas.append({
                    "type": "tool_result",
                    "tool_use_id": bloque.id,
                    "content": str(resultado),
                })

        mensajes.append({"role": "user", "content": resultados_de_herramientas})