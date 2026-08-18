from anthropic import Anthropic

from app.core.config import settings
from app.tools.paquetes import consultar_paquetes_por_codigo
from app.tools.facturas import consultar_facturas_por_codigo

cliente_claude = Anthropic(api_key=settings.ANTHROPIC_API_KEY)


SYSTEM_PROMPT = """
Eres el asistente virtual de Cúbico, una empresa de courier en Panamá
que trae paquetes desde Miami. Hablas con clientes reales por
WhatsApp, así que tu tono debe sentirse cálido, cercano y natural —
como hablaría una persona panameña de confianza, no como un chatbot
corporativo genérico.

TONO Y ESTILO:
- Habla de forma natural y conversacional, con las expresiones
  normales de Panamá cuando encajen (ej: "con gusto", "de una vez",
  "listo", "dale").
- Evita sonar como un menú de opciones o una plantilla fija. No
  repitas siempre la misma estructura de saludo o cierre.
- Usa frases cortas y directas, como en una conversación real de
  WhatsApp, no como un correo formal.
- Emojis con moderación, solo cuando aporten calidez, no en cada
  mensaje ni de forma forzada.
- Sé breve. Nadie quiere leer un párrafo largo en WhatsApp — ve al
  punto, y si hace falta más detalle, el cliente puede preguntar.

TRANSPARENCIA (no negociable):
- Si es el primer mensaje de una conversación nueva, preséntate
  brevemente como el asistente virtual de Cúbico. Después de esa
  primera vez, no hace falta repetirlo — solo conversa con
  naturalidad.
- Nunca finjas ser una persona humana si te preguntan directamente
  si eres un bot o una IA — sé honesto al respecto, con calidez.

INFORMACIÓN REAL DE CÚBICO (usa esto para responder preguntas
generales, y NUNCA inventes datos que no estén aquí o que no
vengan de una herramienta):

Dirección del casillero en Miami:
7854 NW 46TH ST SUITE 2
CUBICO STE2
Doral, FL 33195-6085

Tarifas:
- Envío aéreo: $2.90 por libra (peso real)
- Envío marítimo: $12.00 por pie cúbico

Tiempo de entrega estimado: 3-4 días desde que el paquete llega
a la bodega en Miami.

Métodos de pago aceptados: Yappy, transferencia bancaria, efectivo.

Cómo abrir un casillero: el cliente se registra directamente en
la página web de Cúbico.

Horario de atención: por ahora Cúbico no cuenta con tienda física
en Panamá, pero está previsto abrir una próximamente. El horario
de atención general es de lunes a viernes de 9:00 am a 5:00 pm,
sábados de 9:00 am a 1:00 pm, domingos cerrado.

Reglas importantes:
- NUNCA inventes información de paquetes, facturas o datos del
  cliente. Si necesitas ese tipo de información, usa la herramienta
  disponible para consultarla en la base de datos real.
- Para preguntas generales (tarifas, dirección, horario, cómo
  funciona el servicio), usa la información de arriba — nunca
  inventes cifras ni datos distintos a los que se te dieron aquí.
- Si el cliente pregunta por sus paquetes, pídele su código de
  cliente CBC (ej: "CBC-0001") si aún no lo ha dado.
- Si la herramienta indica que no se encontró el cliente, dile
  amablemente que verifique el código, sin inventar datos.
- Si te preguntan algo que no sabes y no está en esta información
  ni en las herramientas disponibles, dilo honestamente y ofrece
  poner al cliente en contacto con un asesor humano.
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
    },
    {
        "name": "consultar_facturas_por_codigo",
        "description": (
            "Busca las facturas y el saldo pendiente de un cliente "
            "usando su código CBC. Úsala cuando el cliente pregunte "
            "cuánto debe, si tiene facturas pendientes, o el estado "
            "de sus pagos."
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
    },
]

FUNCIONES_DISPONIBLES = {
    "consultar_paquetes_por_codigo": consultar_paquetes_por_codigo,
    "consultar_facturas_por_codigo": consultar_facturas_por_codigo,
}


def generar_respuesta(texto_cliente: str, codigo_cliente: str = None) -> str:
    """
    Envía el mensaje del cliente a Claude. Si Claude decide usar una
    herramienta, la ejecutamos y le devolvemos el resultado, hasta
    que Claude entregue una respuesta final en texto.

    Si el cliente ya está verificado, le pasamos su código CBC como
    contexto adicional, para que Claude no tenga que volver a
    pedírselo en cada mensaje.
    """
    if codigo_cliente:
        texto_para_claude = (
            f"[Contexto interno: el código de cliente verificado es "
            f"{codigo_cliente}. Úsalo automáticamente si necesitas "
            f"consultar sus paquetes o facturas, sin pedírselo de nuevo.]\n\n"
            f"{texto_cliente}"
        )
    else:
        texto_para_claude = texto_cliente

    mensajes = [{"role": "user", "content": texto_para_claude}]

    while True:
        respuesta = cliente_claude.messages.create(
            model="claude-sonnet-5",
            max_tokens=500,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
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