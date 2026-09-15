import time

import httpx

TIMEOUT_SEGUNDOS = 8.0
DURACION_CACHE_SEGUNDOS = 180  # 3 minutos

# Caché en memoria del proceso: numero_tracking -> (guardado_en, resultado).
# Evita golpear el endpoint unificado en cada mensaje si el cliente
# pregunta por el mismo tracking varias veces seguidas.
_cache_tracking: dict[str, tuple[float, dict]] = {}


def consultar_tracking(numero_tracking: str) -> dict:
    """
    Consulta el estado de un paquete contra el endpoint unificado de
    Cúbico (tracking-publico), que ya hace la cascada completa —
    base de datos propia, PTY Freight y bodega de China — y devuelve
    un único resultado indicando de dónde salió ("fuente").
    """
    numero_normalizado = numero_tracking.strip()
    if not numero_normalizado:
        return {
            "encontrado": False,
            "error": True,
            "tipo_error": "tracking_vacio",
            "mensaje": "Falta el número de tracking",
        }

    en_cache = _cache_tracking.get(numero_normalizado)
    if en_cache is not None:
        guardado_en, resultado_cacheado = en_cache
        if time.monotonic() - guardado_en < DURACION_CACHE_SEGUNDOS:
            return resultado_cacheado

    url = f"http://127.0.0.1:3000/api/tracking-publico/{numero_normalizado}"

    try:
        respuesta = httpx.get(url, timeout=TIMEOUT_SEGUNDOS)
        respuesta.raise_for_status()
        datos = respuesta.json()
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            resultado = {
                "encontrado": False,
                "fuente": "no_encontrado",
                "mensaje": "No encontrado en ninguna fuente",
            }
            _cache_tracking[numero_normalizado] = (time.monotonic(), resultado)
            return resultado
        return {
            "encontrado": False,
            "error": True,
            "fuente": "servicio_indisponible",
            "tipo_error": "respuesta_http",
            "codigo_http": error.response.status_code,
            "mensaje": "El servicio de tracking no está disponible temporalmente",
        }
    except httpx.RequestError:
        return {
            "encontrado": False,
            "error": True,
            "fuente": "servicio_indisponible",
            "tipo_error": "conexion",
            "mensaje": "El servicio de tracking no está disponible temporalmente",
        }
    except ValueError:
        return {
            "encontrado": False,
            "error": True,
            "fuente": "servicio_indisponible",
            "tipo_error": "respuesta_invalida",
            "mensaje": "El servicio de tracking devolvió una respuesta inválida",
        }

    resultado = _mapear_respuesta(datos)
    _cache_tracking[numero_normalizado] = (time.monotonic(), resultado)

    return resultado


def _mapear_respuesta(datos: dict) -> dict:
    """
    Traduce la respuesta cruda del endpoint unificado (que trae un
    campo "fuente" distinto según de dónde salió el dato) al formato
    que espera Bruno.
    """
    fuente = datos.get("fuente")

    if fuente == "cubico":
        return {
            "encontrado": True,
            "fuente": "cubico",
            "estado": datos.get("estado"),
            "ruta": datos.get("ruta"),
            "fecha": datos.get("fecha_carga"),
        }

    if fuente == "ptyfreight":
        return {
            "encontrado": True,
            "fuente": "ptyfreight",
            "estado": datos.get("estado_texto"),
            "ubicacion": datos.get("ubicacion"),
        }

    if fuente == "china":
        return {
            "encontrado": True,
            "fuente": "china",
            "estado": datos.get("estado_texto"),
        }

    if fuente == "no_encontrado" or datos.get("encontrado") is False:
        return {
            "encontrado": False,
            "fuente": "no_encontrado",
            "mensaje": "No encontrado en ninguna fuente",
        }

    return {
        "encontrado": False,
        "error": True,
        "fuente": "servicio_indisponible",
        "tipo_error": "fuente_desconocida",
        "mensaje": "El servicio de tracking devolvió una fuente desconocida",
    }
