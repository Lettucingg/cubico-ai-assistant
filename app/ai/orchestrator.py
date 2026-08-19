from anthropic import Anthropic

from app.core.config import settings
from app.tools.paquetes import consultar_paquetes_por_codigo
from app.tools.facturas import consultar_facturas_por_codigo
from app.tools.cotizador import calcular_costo_envio
from app.tools.ptyfreight import consultar_tracking
from app.tools.clientes import verificar_cliente
from app.db.session_store import actualizar_sesion

cliente_claude = Anthropic(api_key=settings.ANTHROPIC_API_KEY)


SYSTEM_PROMPT = """
Eres el encargado de los chat de Cubico llamado Bruno no menciones que eres un asistente virtual, tampoco mencione que eres asistente solo se natura y humano, una empresa de courier en Panamá
que trae paquetes desde Miami. Hablas con clientes reales por
WhatsApp, así que tu tono debe sentirse cálido, cercano y natural —
como hablaría una persona panameña de confianza, no como un chatbot
corporativo genérico, evita usar emojis y preguntar cosas por adelantado solo pregunta en caso tal hay una duda.

TONO Y ESTILO:
- Tu tono es el de un asesor de servicio al cliente profesional pero cercano — cortés, claro y amable, sin sonar acartonado ni excesivamente formal, pero tampoco informal o relajado en exceso.
- Evita jerga muy coloquial o informal (nada de "qué xopa", "bacano", "chévere" en exceso). Puedes usar expresiones panameñas naturales pero moderadas, como "con gusto", "de una vez", "listo".
- Solo separa tu respuesta en varios mensajes cuando haya un cambio real de tema o una lista de puntos distintos que lo justifique. NO dividas cada oración o idea corta en su propio mensaje — eso se siente artificial. Una respuesta de 2-3 oraciones relacionadas debe ir junta, en un solo mensaje.
- Evita sonar como un menú de opciones o una plantilla fija. No repitas siempre la misma estructura de saludo o cierre.
- Sé claro y directo, sin párrafos largos innecesarios, pero sin fragmentar en exceso tampoco.
- Emojis con moderación, casi nunca, solo cuando aporten calidez genuina.
- Si un cliente es grosero o insulta, mantén la calma, no te disculpes de más ni discutas — responde con profesionalismo breve y sigue ofreciendo ayuda real.

TRANSPARENCIA (no negociable):
- Si es el primer mensaje de una conversación nueva, preséntate
  brevemente como el asistente Cúbico llamado Bruno.
- Nunca finjas ser una persona humana si te preguntan directamente
  si eres un bot o una IA.

INFORMACIÓN REAL DE CÚBICO (para preguntas GENERALES, sin necesidad
de verificar identidad — cualquiera puede preguntar esto):

Dirección del casillero en Miami:
7854 NW 46TH ST SUITE 2
CUBICO STE2
Doral, FL 33195-6085

Tarifas:
- Envío aéreo: $2.90 por libra (peso real)
- Envío marítimo: $12.00 por pie cúbico

Cuándo conviene cada tipo de envío (regla exacta, NUNCA la expliques al revés):
- El AÉREO conviene cuando el paquete es LIVIANO pero VOLUMINOSO (poco peso, mucho espacio) — porque se cobra por peso, así que un paquete "esponjoso" sale barato por libra.
- El MARÍTIMO conviene cuando el paquete es PESADO pero COMPACTO (mucho peso, poco espacio) — porque se cobra por volumen, así que un paquete denso aprovecha esa tarifa.
- Para saber cuál conviene en un caso específico, usa la herramienta calcular_costo_envio con ambos tipos y compara los resultados reales — nunca inventes ni "razones" cuál es más barato sin calcularlo.

Tiempo de entrega estimado: 3-4 días desde que el paquete llega
a la bodega en Miami.

Métodos de pago aceptados: Yappy, transferencia bancaria, efectivo.

Cómo abrir un casillero (cliente nuevo, sin cuenta):
https://www.cubico.com.pa/entrar/?tab=registro

Iniciar sesión (cliente que ya tiene cuenta):
https://www.cubico.com.pa/entrar/

Página principal de Cúbico: https://www.cubico.com.pa

Horario de atención: por ahora Cúbico no cuenta con tienda física
en Panamá, pero está previsto abrir una próximamente. El horario
de atención general es de lunes a viernes de 9:00 am a 5:00 pm,
sábados de 9:00 am a 1:00 pm, domingos cerrado.

VERIFICACIÓN DE IDENTIDAD (solo para datos personales):
- Preguntas GENERALES (tarifas, dirección, horario, cómo funciona
  el servicio, cómo registrarse) — respóndelas SIEMPRE directo, sin
  pedir ningún dato de identidad. Cualquier persona puede preguntar
  esto, sea cliente o no.
- Preguntas sobre DATOS PERSONALES del cliente (sus paquetes, sus
  facturas, su saldo) — estas SÍ requieren verificar identidad
  primero. Si en el contexto de este mensaje no se te dio un código
  de cliente ya verificado, pídele al cliente su código CBC
  (ej: CBC-0001) y el correo con el que está registrado. Cuando te
  los dé, usa la herramienta verificar_identidad_cliente. Si la
  verificación falla, pídele que lo intente de nuevo. Si tiene
  éxito, ya puedes usar las herramientas de paquetes/facturas con
  ese código.

ESCALAMIENTO A HUMANO:
- Cuando uses la herramienta escalar_a_humano, informa al cliente de
  forma simple y segura, por ejemplo: "Déjame consultarlo con el
  equipo y revisar bien en el sistema, te confirmo en breve" o
  similar.
- NUNCA expliques por qué no puedes resolverlo tú mismo (no digas
  cosas como "no tengo acceso a eso", "el sistema no me permite",
  "ellos tienen más información que yo"). Simplemente confirma que
  lo vas a revisar, con confianza y sin explicar limitaciones
  internas.

Reglas importantes:
- NUNCA inventes información de paquetes, facturas o datos del
  cliente. Usa siempre las herramientas para eso.
- Nunca inventes tarifas ni datos distintos a los de arriba.
- Si te preguntan algo que no sabes, dilo honestamente y ofrece
  poner al cliente en contacto con un asesor humano.
"""

HERRAMIENTAS = [
    {
        "name": "verificar_identidad_cliente",
        "description": (
            "Verifica la identidad de un cliente usando su código "
            "CBC y su correo electrónico registrado. Úsala antes de "
            "consultar paquetes o facturas, si el cliente todavía "
            "no está verificado en esta conversación."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "codigo_cliente": {
                    "type": "string",
                    "description": "El código CBC del cliente, ej: CBC-0001",
                },
                "email": {
                    "type": "string",
                    "description": "El correo electrónico registrado del cliente",
                },
            },
            "required": ["codigo_cliente", "email"],
        },
    },
    {
        "name": "consultar_paquetes_por_codigo",
        "description": (
            "Busca los paquetes de un cliente YA VERIFICADO usando "
            "su código CBC."
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
            "YA VERIFICADO usando su código CBC."
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
        "name": "calcular_costo_envio",
        "description": (
            "Calcula el costo estimado de un envío. No requiere "
            "verificación — cualquiera puede pedir una cotización."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo_envio": {"type": "string", "description": "'aereo' o 'maritimo'"},
                "peso_libras": {"type": "number", "description": "Peso en libras (aéreo)"},
                "pies_cubicos": {"type": "number", "description": "Pies cúbicos (marítimo)"},
            },
            "required": ["tipo_envio"],
        },
    },
    {
        "name": "consultar_tracking",
        "description": (
            "Consulta el estado de tracking en tiempo real de un "
            "paquete específico. No requiere verificación de "
            "identidad del cliente, solo el número de tracking."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "numero_tracking": {"type": "string", "description": "Número de tracking"},
                "tipo_envio": {"type": "string", "description": "'aereo' o 'maritimo'"},
            },
            "required": ["numero_tracking"],
        },
    },
    {
        "name": "escalar_a_humano",
        "description": (
            "Marca la conversación para que un asesor humano de Cúbico "
            "intervenga. Úsala SOLO cuando: el cliente pide "
            "explícitamente hablar con una persona/asesor humano, "
            "muestra frustración CLARA Y SOSTENIDA (varios mensajes "
            "negativos seguidos, no un insulto aislado), tiene una "
            "queja o reclamo formal específico (paquete perdido, "
            "dañado, cobro incorrecto), o no tienes ninguna "
            "herramienta ni información para resolver lo que "
            "pregunta. Un insulto o comentario negativo aislado, sin "
            "un problema real de fondo detrás, NO amerita escalar de "
            "inmediato — responde con calma y sigue ofreciendo ayuda "
            "primero."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "motivo": {
                    "type": "string",
                    "description": "Resumen breve de por qué se está escalando",
                }
            },
            "required": ["motivo"],
        },
    },
]

def buscar_respuesta_fija(texto_cliente: str) -> str | None:
    """
    Revisa si el mensaje coincide con una pregunta muy frecuente y
    genérica, para responder sin gastar tokens de la API de Claude.
    """
    texto = texto_cliente.lower().strip()

    if any(frase in texto for frase in ["cuanto cuesta el envio", "cuánto cuesta el envío", "precio del envio", "tarifa aerea", "tarifa aérea", "tarifa maritima", "tarifa marítima"]):
        return (
            "¡Con gusto! 📦\n\n"
            "Aéreo: $2.90 por libra (peso real)\n\n"
            "Marítimo: $12.00 por pie cúbico\n\n"
            "¿Necesitas que te calcule un envío específico?"
        )

    if any(frase in texto for frase in ["direccion de miami", "dirección de miami", "cual es la direccion", "cuál es la dirección"]):
        return (
            "Esta es la dirección de tu casillero en Miami:\n\n"
            "7854 NW 46TH ST SUITE 2\n"
            "CUBICO STE2\n"
            "Doral, FL 33195-6085"
        )

    if any(frase in texto for frase in ["como me registro", "cómo me registro", "como abro mi casillero", "cómo abro mi casillero"]):
        return (
            "Es bien fácil, regístrate aquí:\n\n"
            "https://www.cubico.com.pa/entrar/?tab=registro\n\n"
            "Ahí te crean tu casillero con la dirección en Miami."
        )

    if any(frase in texto for frase in ["cual es el horario", "cuál es el horario", "que horario tienen", "qué horario tienen"]):
        return (
            "Nuestro horario de atención:\n\n"
            "Lunes a viernes: 9:00 am - 5:00 pm\n"
            "Sábados: 9:00 am - 1:00 pm\n"
            "Domingos: cerrado"
        )

    return None


def generar_respuesta(texto_cliente: str, telefono: str, codigo_cliente: str = None, historial: list = None) -> str:

    """
    Envía el mensaje del cliente a Claude, con el historial de la
    conversación. Claude decide libremente si necesita verificar
    identidad (usando la herramienta verificar_identidad_cliente)
    antes de consultar datos personales.
    """

    respuesta_fija = buscar_respuesta_fija(texto_cliente)
    if respuesta_fija:
        return respuesta_fija
    def _verificar_identidad(codigo_cliente, email):
        if verificar_cliente(codigo_cliente, email):
            actualizar_sesion(telefono, estado="verificado", codigo_cliente_verificado=codigo_cliente)
            return {"verificado": True, "codigo_cliente": codigo_cliente}
        return {"verificado": False, "mensaje": "El código y correo no coinciden."}

    def _escalar_a_humano(motivo):
        actualizar_sesion(telefono, necesita_atencion_humana=True, motivo_escalamiento=motivo)
        return {"escalado": True, "mensaje": "Un asesor será notificado y te contactará pronto."}

    funciones_disponibles = {
        "verificar_identidad_cliente": lambda codigo_cliente, email: _verificar_identidad(codigo_cliente, email),
        "consultar_paquetes_por_codigo": consultar_paquetes_por_codigo,
        "consultar_facturas_por_codigo": consultar_facturas_por_codigo,
        "calcular_costo_envio": calcular_costo_envio,
        "consultar_tracking": consultar_tracking,
        "escalar_a_humano": _escalar_a_humano,
    }

    if codigo_cliente:
        texto_para_claude = (
            f"[Contexto interno: el código de cliente ya verificado es "
            f"{codigo_cliente}. Puedes usarlo directamente en las "
            f"herramientas de paquetes/facturas sin volver a "
            f"verificar.]\n\n{texto_cliente}"
        )
    else:
        texto_para_claude = texto_cliente

    mensajes = list(historial) if historial else []
    mensajes.append({"role": "user", "content": texto_para_claude})

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
            for bloque in respuesta.content:
                if bloque.type == "text":
                    return bloque.text
            return (
                "Disculpa, no pude generar una respuesta en este momento. "
                "¿Puedes intentar de nuevo?"
            )

        mensajes.append({"role": "assistant", "content": respuesta.content})

        resultados_de_herramientas = []
        for bloque in respuesta.content:
            if bloque.type == "tool_use":
                funcion = funciones_disponibles[bloque.name]
                resultado = funcion(**bloque.input)

                resultados_de_herramientas.append({
                    "type": "tool_result",
                    "tool_use_id": bloque.id,
                    "content": str(resultado),
                })
        mensajes.append({"role": "user", "content": resultados_de_herramientas})


def redactar_respuesta_de_asesor(texto_cliente_original: str, solucion_del_asesor: str) -> str:
    """
    Redacta, con el tono normal de Bruno, el mensaje final para un
    cliente cuyo caso fue resuelto por un asesor humano — como si
    Bruno mismo lo hubiera resuelto, sin mencionar que un humano
    intervino.
    """
    prompt = (
        "Un asesor humano del equipo de Cúbico ya resolvió el caso de "
        "este cliente. Redacta el mensaje final que se le va a enviar "
        "por WhatsApp, con tu tono normal, incorporando la solución "
        "que dio el asesor como si tú mismo la hubieras resuelto. "
        "NUNCA menciones que un humano o un asesor intervino — "
        "responde como si fueras tú quien resolvió todo.\n\n"
        f"Mensaje original del cliente: \"{texto_cliente_original}\"\n\n"
        f"Solución que dio el asesor: \"{solucion_del_asesor}\"\n\n"
        "Escribe solo el mensaje final para el cliente, listo para enviar."
    )

    respuesta = cliente_claude.messages.create(
        model="claude-sonnet-5",
        max_tokens=500,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": prompt}],
    )

    for bloque in respuesta.content:
        if bloque.type == "text":
            return bloque.text

    return solucion_del_asesor
