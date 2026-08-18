import httpx


def consultar_tracking(numero_tracking: str, tipo_envio: str = "aereo") -> dict:
    """
    Consulta el estado de tracking en tiempo real de un paquete,
    directamente contra la API pública de ptyfreight.com.

    A diferencia de las otras herramientas, esta no consulta la
    base de datos de Cúbico — consulta un servicio EXTERNO en
    tiempo real, así que la información puede variar en cada
    llamada (por ejemplo, si el paquete avanzó de estado).
    """
    tipo_envio = tipo_envio.strip().lower()

    if tipo_envio in ("maritimo", "marítimo"):
        url = f"https://ptyfreight.com/api/ocean-tracking/{numero_tracking}"
    else:
        url = f"https://ptyfreight.com/api/tracking/{numero_tracking}"

    try:
        respuesta = httpx.get(url, timeout=10.0)

        if respuesta.status_code != 200:
            return {
                "encontrado": False,
                "mensaje": (
                    f"No se pudo consultar el tracking {numero_tracking} "
                    f"en este momento."
                ),
            }

        return {
            "encontrado": True,
            "datos": respuesta.json(),
        }

    except httpx.RequestError:
        return {
            "encontrado": False,
            "mensaje": (
                "El servicio de tracking no está disponible en este "
                "momento. Intenta de nuevo más tarde."
            ),
        }