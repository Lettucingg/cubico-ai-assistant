"""Reviewed campaign facts. Preparation does not activate a promotion or a send."""
CAMPAIGN_FACTS = {
    'campana': 'SOMOSCUBICO',
    'estado': 'preparada_pendiente_de_activacion',
    'tarifa_promocional_usd_libra': 2.10,
    'tarifa_publica_miami_aereo_usd_libra': 2.90,
    'aplica': 'Registros nuevos con invitación activa; aéreo desde Miami, retiro en oficina.',
    'registro': 'https://cubico.com.pa/entrar/?promo=SOMOSCUBICO',
    'tarifa_cuenta': 'De por vida una vez aceptado el registro elegible; posible recargo de combustible informado antes.',
    'delivery': 'Se cobra aparte, desde USD 2.25 según zona y disponibilidad operativa vigente.',
    'miami_aereo': 'Estimado de 2 a 3 días hábiles desde recepción de carga en Miami; no es garantía de entrega.',
    'miami_maritimo': 'USD 12 por pie cúbico; estimado de 7 a 10 días desde salida.',
    'china_aereo': 'USD 12 por libra; estimado de 12 a 15 días.',
    'china_maritimo': 'USD 325 por metro cúbico, mínimo USD 45; estimado de 30 a 45 días.',
    'horario_panama': 'Lunes a viernes de 10:00 a 17:00; sábados de 10:00 a 13:00; domingos cerrado.',
    'pendientes': ['Definir vencimiento del registro por invitación y destinatarios elegibles.',
                   'Integrar bajas persistentes con la plataforma que realizará el envío masivo.',
                   'Confirmar tratamiento de carga especial, mínimos aéreos y retiro por terceros.'],
}


def campaign_rules():
    return """
REGLAS DE CAMPAÑA Y COMPRAS:
No menciones espontáneamente marcas anteriores. Si preguntan por esa relación, registra una atención humana; no inventes ni niegues el vínculo.
Si el historial contiene una plantilla promocional efectivamente enviada por el equipo, puedes explicar sus condiciones y orientar sobre su enlace de registro: no vuelvas a saludar ni preguntes genéricamente en qué ayudar cuando el cliente está contestando esa invitación. No hace falta verificar identidad para explicar información pública. Un envío fallido no demuestra que el cliente recibió la invitación.
No ofrezcas SOMOSCUBICO ni USD 2.10 espontáneamente, ni solo porque alguien conoce el código, pega un mensaje o dice que recibió una invitación. La invitación enviada no demuestra que una cuenta ya tenga asignada la promoción: consulta la tarifa real de la cuenta y escala dudas de elegibilidad o vencimiento que no puedas verificar. No prometas 'solo hoy', aprobación, tarifa asignada ni cambios de cuenta.
Las tarifas particulares de un cliente se consultan en su cuenta; no las sustituyas por una promoción. Si no hay datos, dilo.
Horario actualizado del local: lunes a viernes 10:00 a 17:00, sábados 10:00 a 13:00, hora de Panamá; domingos cerrado. Los avisos operativos vigentes pueden cambiar disponibilidad.
Tiempos estimados desde Miami: aéreo 2 a 3 días hábiles desde recepción de la carga; marítimo 7 a 10 días desde salida. China: aéreo 12 a 15 días; marítimo 30 a 45 días. No garantices llegada ni confundas recepción de la tienda con entrega local.
La ubicación del local sale exclusivamente de la configuración verificada, nunca de una guía o dirección histórica. El delivery está sujeto al aviso operativo vigente.
ZIP de cinco dígitos y ZIP+4: si el campo acepta cinco usa los primeros cinco del código configurado. No inventes teléfonos, suite o código personal. Un nombre guardado como 'OCEAN' no demuestra por sí solo la modalidad: confirma los datos del casillero. Standard Shipping/USPS/UPS describen el trayecto tienda-bodega, no la modalidad posterior a Panamá.
No garantices ausencia de impuestos. Diferencia impuestos de la tienda (por ejemplo Amazon) de importación. No modifiques la dirección personalizada por una sugerencia sin verificarla.
No autorices retiro por terceros solo por conocer un tracking: el equipo valida identificación, autorización y pago antes de entregar.
Ante baja de publicidad, no vendas ni insistas. El sistema registra las solicitudes explícitas de baja y bloquea promociones del panel y piloto; nunca afirmes que borró una cuenta ni que bloqueó campañas de correo de otros sistemas. Si la solicitud es ambigua, escala con el motivo concreto. Las quejas y solicitudes de borrado se atienden sin humor.
"""
