import re
import time

import httpx

TIMEOUT_SEGUNDOS = 8.0
DURACION_CACHE_SEGUNDOS = 180  # 3 minutos

# Etiquetas tomadas de /public/assets/tracking.js del sistema de Cúbico.
# Su catálogo es provisional: solo el estado 0 indica una ubicación concreta.
# Los estados externos 3 y 4 no prueban retiro ni entrega al cliente de Cúbico.
ESTADOS_TRACKING = {
    "0": "Recibido en Miami",
    "1": "En proceso",
    "2": "En tránsito",
    "3": "Registro actualizado como disponible; retiro en nuestro local sin confirmar",
    "4": "Registro marcado como entregado o cerrado; entrega al cliente sin confirmar",
}

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
    if not resultado.get("error"):
        _cache_tracking[numero_normalizado] = (time.monotonic(), resultado)

    return resultado


def _mapear_respuesta(datos: dict) -> dict:
    """
    Traduce la respuesta cruda del endpoint unificado (que trae un
    campo "fuente" distinto según de dónde salió el dato) al formato
    que espera Bruno.
    """
    if not isinstance(datos, dict):
        return _respuesta_pty_invalida()
    fuente = datos.get("fuente")

    if fuente == "cubico":
        return {
            "encontrado": True,
            "fuente": "cubico",
            "estado": datos.get("estado"),
            "ruta": datos.get("ruta"),
            "fecha": datos.get("fecha_carga"),
        }

    if fuente == "pty" or (fuente == "ptyfreight" and "pty" in datos):
        return _mapear_pty(datos.get("pty"))

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


def _respuesta_pty_invalida() -> dict:
    return {
        "encontrado": False,
        "error": True,
        "fuente": "servicio_indisponible",
        "tipo_error": "respuesta_invalida",
        "mensaje": "El servicio de tracking devolvió una respuesta incompleta o inválida",
    }


def _mapear_pty(pty: dict) -> dict:
    """Traduce los estados con el mismo criterio de la página de tracking de Cúbico."""
    if not isinstance(pty, dict) or pty.get("status") != "ok":
        return _respuesta_pty_invalida()
    paquetes = pty.get("packages")
    if not isinstance(paquetes, list) or not paquetes:
        return _respuesta_pty_invalida()

    registros = []
    estados = []
    for paquete in paquetes:
        if not isinstance(paquete, dict):
            return _respuesta_pty_invalida()
        registro = {}
        mal_identificado = any(
            isinstance(paquete.get(campo), str)
            and re.search(r"(?<![a-z0-9])malid(?![a-z0-9])", paquete[campo], re.IGNORECASE)
            for campo in ("ware_house", "warehouse_number")
        )
        if mal_identificado:
            registro["identificacion_incorrecta"] = True
        estado_crudo = paquete.get("state")
        codigo = str(estado_crudo) if type(estado_crudo) in (int, str) else None
        estado = codigo if codigo in ESTADOS_TRACKING else None
        estados.append(estado)
        if estado is not None:
            registro["estado"] = ESTADOS_TRACKING[estado]
        fecha = paquete.get("date_of_admission")
        if isinstance(fecha, str) and fecha.strip():
            registro["fecha_ingreso_proveedor"] = fecha
        if isinstance(paquete.get("is_processed"), bool):
            registro["procesado_por_proveedor"] = paquete["is_processed"]
        if not registro:
            return _respuesta_pty_invalida()
        registros.append(registro)

    mismo_estado = estados[0] is not None and all(e == estados[0] for e in estados)
    resultado = {
        "encontrado": True,
        "fuente": "ptyfreight",
        "estado": (
            ESTADOS_TRACKING[estados[0]] if mismo_estado
            else "Tracking registrado; ubicación actual pendiente de confirmar"
        ),
        "disponibilidad_local_confirmada": False,
        "entrega_cliente_confirmada": False,
        "registros_proveedor": registros,
        "advertencia": (
            "Las fechas son de ingreso en el proveedor. El procesamiento no confirma "
            "ubicación, salida hacia Panamá ni entrega. No interpretes códigos de "
            "bodega como ubicaciones. Los estados disponible o cerrado no confirman "
            "retiro en nuestro local ni entrega al cliente. Si los registros tienen "
            "estados distintos o desconocidos, confirma con el equipo la ubicación actual."
        ),
    }
    if mismo_estado and estados[0] == "0":
        resultado["ubicacion"] = "Miami"
    if any(r.get("identificacion_incorrecta") for r in registros):
        resultado["identificacion_incorrecta"] = True
        resultado["requiere_revision_humana"] = True
        resultado["advertencia_cliente"] = (
            "El paquete aparece mal identificado y necesita revisión para asociarlo "
            "correctamente a tu cuenta."
        )
    return resultado
