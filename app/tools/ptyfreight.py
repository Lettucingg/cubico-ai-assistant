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
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError):
        return {
            "encontrado": False,
            "mensaje": "No se pudo consultar el estado",
        }

    resultado = _mapear_respuesta(datos)
    _cache_tracking[numero_normalizado] = (time.monotonic(), resultado)

    return resultado


ESTADOS_CUBICO = {
    "notificado": "llegó a Cúbico Panamá y está listo para retiro o entrega",
    "en_ruta": "está en camino hacia Panamá",
    "entregado": "fue entregado al cliente",
    "en_miami": "está en nuestra bodega en Miami siendo procesado",
}


def _mapear_respuesta(datos: dict) -> dict:
    """
    Traduce la respuesta cruda del endpoint unificado (que trae un
    campo "fuente" distinto según de dónde salió el dato) al formato
    que espera Bruno.
    """
    fuente = datos.get("fuente")

    if fuente == "cubico":
        estado_raw = datos.get("estado", "")
        estado_texto = ESTADOS_CUBICO.get(estado_raw, estado_raw)
        ruta = datos.get("ruta", "")
        return {
            "encontrado": True,
            "fuente": "cubico",
            "estado": estado_raw,
            "estado_texto": estado_texto,
            "ruta": ruta,
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

    return {
        "encontrado": False,
        "mensaje": "No encontrado en ninguna fuente",
    }
