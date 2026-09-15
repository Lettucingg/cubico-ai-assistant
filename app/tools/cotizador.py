import math

TARIFA_AEREA_POR_LIBRA = 2.90
TARIFA_MARITIMA_POR_PIE_CUBICO = 12.00
TARIFA_CHINA_AEREA_POR_LIBRA = 12.00
TARIFA_CHINA_MARITIMA_POR_CBM = 325.00
MINIMO_CHINA_MARITIMO = 45.00

CM_A_PULGADAS = 0.393701


def calcular_costo_envio(
    tipo_envio: str,
    peso_libras: float = None,
    alto: float = None,
    ancho: float = None,
    largo: float = None,
    unidad_medida: str = "pulgadas",
    origen: str = "miami",
    volumen_cbm: float = None,
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
    origen = (origen or "miami").strip().lower()
    if origen not in {"miami", "china"}:
        return {"error": True, "mensaje": "El origen debe ser 'miami' o 'china'."}

    if tipo_envio == "aereo" or tipo_envio == "aéreo":
        peso_volumetrico_libras = None
        if origen == "china" and all(valor is not None for valor in (alto, ancho, largo)):
            unidad = (unidad_medida or "cm").strip().lower()
            if unidad in ("cm", "centimetros", "centímetros"):
                alto_cm, ancho_cm, largo_cm = alto, ancho, largo
            elif unidad in ("pulgadas", "in", "inches"):
                alto_cm, ancho_cm, largo_cm = alto / CM_A_PULGADAS, ancho / CM_A_PULGADAS, largo / CM_A_PULGADAS
            else:
                return {"error": True, "mensaje": "La unidad de medida debe ser 'pulgadas' o 'cm'."}
            peso_volumetrico_libras = (alto_cm * ancho_cm * largo_cm / 5000) * 2.205

        if peso_libras is None and peso_volumetrico_libras is None:
            return {
                "error": True,
                "mensaje": "Para calcular el envío aéreo necesito el peso en libras o las medidas.",
            }

        peso_cobrable = max(peso_libras or 0, peso_volumetrico_libras or 0)
        peso_redondeado = math.ceil(peso_cobrable)
        tarifa = TARIFA_CHINA_AEREA_POR_LIBRA if origen == "china" else TARIFA_AEREA_POR_LIBRA
        costo = round(peso_redondeado * tarifa, 2)

        return {
            "error": False,
            "tipo_envio": "aéreo",
            "origen": origen,
            "peso_libras_original": peso_libras,
            "peso_volumetrico_libras": round(peso_volumetrico_libras, 4) if peso_volumetrico_libras is not None else None,
            "peso_cobrable_libras": round(peso_cobrable, 4),
            "peso_libras_redondeado": peso_redondeado,
            "tarifa_por_libra": tarifa,
            "costo_estimado": costo,
        }

    elif tipo_envio == "maritimo" or tipo_envio == "marítimo":
        if origen == "china":
            if volumen_cbm is None and all(valor is not None for valor in (alto, ancho, largo)):
                unidad = (unidad_medida or "cm").strip().lower()
                if unidad in ("cm", "centimetros", "centímetros"):
                    volumen_cbm = (alto * ancho * largo) / 1_000_000
                elif unidad in ("pulgadas", "in", "inches"):
                    volumen_cbm = ((alto * CM_A_PULGADAS) * (ancho * CM_A_PULGADAS) * (largo * CM_A_PULGADAS)) / 1_000_000
                else:
                    return {"error": True, "mensaje": "La unidad de medida debe ser 'pulgadas' o 'cm'."}
            if volumen_cbm is None:
                return {
                    "error": True,
                    "mensaje": "Para calcular el marítimo desde China necesito el CBM total o las tres medidas.",
                }
            if volumen_cbm <= 0:
                return {"error": True, "mensaje": "El volumen CBM debe ser mayor que cero."}
            # Cúbico factura China marítimo subiendo el CBM a dos decimales.
            volumen_facturable = math.ceil((volumen_cbm - 1e-12) * 100) / 100
            subtotal = round(volumen_facturable * TARIFA_CHINA_MARITIMA_POR_CBM, 2)
            costo = max(subtotal, MINIMO_CHINA_MARITIMO)
            return {
                "error": False,
                "tipo_envio": "marítimo",
                "origen": "china",
                "volumen_cbm_original": volumen_cbm,
                "volumen_cbm_facturable": volumen_facturable,
                "tarifa_por_cbm": TARIFA_CHINA_MARITIMA_POR_CBM,
                "costo_minimo": MINIMO_CHINA_MARITIMO,
                "costo_estimado": costo,
            }

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
            "origen": "miami",
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
