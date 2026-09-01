import math

TARIFA_AEREA_POR_LIBRA = 2.90
TARIFA_MARITIMA_POR_PIE_CUBICO = 12.00

CM_A_PULGADAS = 0.393701


def calcular_costo_envio(
    tipo_envio: str,
    peso_libras: float = None,
    alto: float = None,
    ancho: float = None,
    largo: float = None,
    unidad_medida: str = "pulgadas",
) -> dict:
    """
    Calcula el costo estimado de un envío, según el tipo (aéreo o
    marítimo).

    - Aéreo: se cobra por peso en libras. El peso se redondea SIEMPRE
      hacia arriba (ceiling) al siguiente entero antes de calcular el
      costo.
    - Marítimo: se cobra por pies cúbicos, calculados a partir de las
      medidas del paquete (alto x ancho x largo). Las medidas deben
      estar en pulgadas; si vienen en centímetros se convierten
      primero. El resultado en pies cúbicos también se redondea
      SIEMPRE hacia arriba antes de calcular el costo.

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

        peso_redondeado = math.ceil(peso_libras)
        costo = round(peso_redondeado * TARIFA_AEREA_POR_LIBRA, 2)

        return {
            "error": False,
            "tipo_envio": "aéreo",
            "peso_libras_original": peso_libras,
            "peso_libras_redondeado": peso_redondeado,
            "tarifa_por_libra": TARIFA_AEREA_POR_LIBRA,
            "costo_estimado": costo,
        }

    elif tipo_envio == "maritimo" or tipo_envio == "marítimo":
        if alto is None or ancho is None or largo is None:
            return {
                "error": True,
                "mensaje": (
                    "Para calcular el envío marítimo necesito las tres "
                    "medidas del paquete: alto, ancho y largo."
                ),
            }

        unidad_medida = (unidad_medida or "pulgadas").strip().lower()
        medidas_originales = {"alto": alto, "ancho": ancho, "largo": largo, "unidad": unidad_medida}

        if unidad_medida in ("cm", "centimetros", "centímetros"):
            alto_in = alto * CM_A_PULGADAS
            ancho_in = ancho * CM_A_PULGADAS
            largo_in = largo * CM_A_PULGADAS
        elif unidad_medida in ("pulgadas", "in", "inches"):
            alto_in = alto
            ancho_in = ancho
            largo_in = largo
        else:
            return {
                "error": True,
                "mensaje": "La unidad de medida debe ser 'pulgadas' o 'cm'.",
            }

        pies_cubicos_exactos = (alto_in * ancho_in * largo_in) / 1728
        pies_cubicos_redondeados = math.ceil(pies_cubicos_exactos)
        costo = round(pies_cubicos_redondeados * TARIFA_MARITIMA_POR_PIE_CUBICO, 2)

        return {
            "error": False,
            "tipo_envio": "marítimo",
            "medidas_originales": medidas_originales,
            "medidas_en_pulgadas": {"alto": alto_in, "ancho": ancho_in, "largo": largo_in},
            "pies_cubicos_exactos": round(pies_cubicos_exactos, 4),
            "pies_cubicos_redondeados": pies_cubicos_redondeados,
            "tarifa_por_pie_cubico": TARIFA_MARITIMA_POR_PIE_CUBICO,
            "costo_estimado": costo,
        }

    else:
        return {
            "error": True,
            "mensaje": "El tipo de envío debe ser 'aereo' o 'maritimo'.",
        }
