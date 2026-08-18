TARIFA_AEREA_POR_LIBRA = 2.90
TARIFA_MARITIMA_POR_PIE_CUBICO = 12.00


def calcular_costo_envio(tipo_envio: str, peso_libras: float = None, pies_cubicos: float = None) -> dict:
    """
    Calcula el costo estimado de un envío, según el tipo (aéreo o
    marítimo) y la cantidad correspondiente (libras para aéreo,
    pies cúbicos para marítimo).

    Esta es una función de cálculo puro, sin acceso a base de datos.
    Se trata como "herramienta" para que el número salga siempre de
    este código determinístico, no de que Claude intente calcularlo
    por su cuenta (lo cual podría llevar a errores de cálculo).
    """
    tipo_envio = tipo_envio.strip().lower()

    if tipo_envio == "aereo" or tipo_envio == "aéreo":
        if peso_libras is None:
            return {
                "error": True,
                "mensaje": "Para calcular el envío aéreo necesito el peso en libras.",
            }
        costo = round(peso_libras * TARIFA_AEREA_POR_LIBRA, 2)
        return {
            "error": False,
            "tipo_envio": "aéreo",
            "peso_libras": peso_libras,
            "tarifa_por_libra": TARIFA_AEREA_POR_LIBRA,
            "costo_estimado": costo,
        }

    elif tipo_envio == "maritimo" or tipo_envio == "marítimo":
        if pies_cubicos is None:
            return {
                "error": True,
                "mensaje": "Para calcular el envío marítimo necesito el tamaño en pies cúbicos.",
            }
        costo = round(pies_cubicos * TARIFA_MARITIMA_POR_PIE_CUBICO, 2)
        return {
            "error": False,
            "tipo_envio": "marítimo",
            "pies_cubicos": pies_cubicos,
            "tarifa_por_pie_cubico": TARIFA_MARITIMA_POR_PIE_CUBICO,
            "costo_estimado": costo,
        }

    else:
        return {
            "error": True,
            "mensaje": "El tipo de envío debe ser 'aereo' o 'maritimo'.",
        }