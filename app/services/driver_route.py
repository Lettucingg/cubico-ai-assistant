"""Plan personal de carga y navegación. No escribe en facturación o despachos."""
import hashlib
import json
import math
import re
from datetime import date, datetime

from sqlalchemy.exc import IntegrityError
from app.db import session_store as store
from app.services.delivery_cases import hoy, ubicacion_segura

ZONAS = {"todas", "centro", "este", "otra", "por_definir"}


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def validar_filtros(fecha, zona):
    if not isinstance(fecha, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha):
        raise ValueError("Selecciona una fecha válida")
    try:
        date.fromisoformat(fecha)
    except ValueError:
        raise ValueError("Selecciona una fecha válida") from None
    if not isinstance(zona, str) or zona not in ZONAS:
        raise ValueError("Selecciona una zona válida")


def _clave(usuario, fecha, zona):
    return _hash([usuario, fecha])


def _parada(solicitud):
    ficha = solicitud.get("ficha_domicilio") or {}
    motivos = []
    if solicitud.get("requiere_verificacion"):
        motivos.append("Verificar cliente")
    if solicitud.get("requiere_factura"):
        motivos.append("Asociar factura")
    saldo = solicitud.get("monto_pendiente")
    try:
        pago_verificado = bool(solicitud.get("pago_resuelto")) and saldo is not None and not isinstance(saldo, bool) and math.isfinite(float(saldo)) and float(saldo) <= .01
    except (ValueError, TypeError):
        pago_verificado = False
    if not pago_verificado:
        motivos.append("Revisar pago en facturación")
    if not solicitud.get("paquetes_preparados"):
        motivos.append("Preparar paquetes")
    if not solicitud.get("domicilio_coordinado"):
        motivos.append("Confirmar coordinación")
    motivos.extend(ficha.get("faltantes") or [])
    if not ficha.get("listo_para_coordinar") and not ficha.get("faltantes"):
        motivos.append("Revisar ficha de domicilio")
    trackings = list(dict.fromkeys(p.strip() for p in re.split(r"[,;\n]+", solicitud.get("paquetes") or "") if p.strip()))
    if not trackings:
        motivos.append("Identificar paquetes")
    phone = str(solicitud.get("telefono") or "")
    if not re.fullmatch(r"[1-9]\d{7,14}", phone):
        motivos.append("Revisar teléfono")
    map_url = ficha.get("ubicacion_url") or ""
    data = {
        "id": ficha.get("clave") or _hash([phone, solicitud.get("codigo_cliente"), trackings]),
        "telefono": phone, "nombre": solicitud.get("nombre") or phone,
        "codigo_cliente": solicitud.get("codigo_cliente"), "trackings": trackings,
        "direccion": ficha.get("direccion") or solicitud.get("direccion") or "",
        "barrio": ficha.get("barrio") or "", "zona": ficha.get("zona") or "por_definir",
        "referencias": ficha.get("referencias") or "",
        "ubicacion_url": map_url if ubicacion_segura(map_url) else "",
        "fecha_confirmada": ficha.get("fecha_confirmada") or "",
        "hora_desde": ficha.get("hora_desde") or "", "hora_hasta": ficha.get("hora_hasta") or "",
        "dia_solicitado": ficha.get("dia_solicitado") or "",
        "fecha_solicitada": ficha.get("fecha_solicitada") or "",
        "horario_solicitado": ficha.get("horario_solicitado") or "",
        "prioridad": ficha.get("prioridad") or "normal", "motivo_prioridad": ficha.get("motivo_prioridad") or "",
        "pago_verificado": pago_verificado,
        "lista": not motivos, "pendientes": list(dict.fromkeys(motivos)),
    }
    # Cambiar los paquetes, el saldo o la ficha invalida la verificación de carga.
    data["huella"] = _hash([data, ficha.get("token")])
    return data


def construir_ruta(solicitudes, usuario, fecha, zona="todas", suspension=None):
    validar_filtros(fecha, zona)
    with store.SessionSesiones() as db:
        fila = db.query(store.PlanRuta).filter_by(clave=_clave(usuario, fecha, zona)).first()
        datos = json.loads(fila.datos_json) if fila else {}
        revision = fila.revision if fila else 0
        actualizado = fila.actualizado_en.isoformat() + "Z" if fila else None
    programadas, sin_programar = [], []
    for s in solicitudes:
        if s.get("tipo") != "domicilio":
            continue
        p = _parada(s)
        if zona != "todas" and p["zona"] != zona:
            continue
        if not p["fecha_confirmada"]:
            sin_programar.append(p)
        elif p["fecha_confirmada"] == fecha:
            programadas.append(p)
    # Horas explícitas primero, luego prioridad. No es una optimización por tráfico.
    programadas.sort(key=lambda p: (p["hora_desde"] or "99:99", p["prioridad"] != "alta", p["zona"], p["nombre"].casefold(), p["id"]))
    orden = {key: i for i, key in enumerate(datos.get("orden", []))}
    listas = [p for p in programadas if p["lista"]]
    listas.sort(key=lambda p: orden.get(p["id"], len(orden)))
    cargadas = datos.get("cargadas", {})
    for p in listas:
        p["cargada"] = cargadas.get(p["id"]) == p["huella"]
    pendientes = [p for p in programadas if not p["lista"]]
    faltan_carga = sum(not p["cargada"] for p in listas)
    bloqueos = []
    if fecha != hoy().isoformat():
        bloqueos.append("El modo de recorrido está disponible para hoy")
    if date.fromisoformat(fecha).weekday() >= 5:
        bloqueos.append("No hay domicilios los sábados ni domingos")
    if not listas:
        bloqueos.append("No hay entregas listas para esta fecha y zona")
    if faltan_carga:
        bloqueos.append("Verifica los paquetes cargados antes de abrir el recorrido")
    if suspension:
        bloqueos.append("Domicilios suspendidos: revisa Situación actual y avisos")
    token = _hash([usuario, fecha, zona, revision, sorted((p["id"], p["huella"]) for p in programadas), bool(suspension)])
    return {
        "fecha": fecha, "hoy": hoy().isoformat(), "zona": zona, "usuario": usuario,
        "token": token, "revision": revision, "actualizado_en": actualizado,
        "consultado_en": datetime.utcnow().isoformat() + "Z",
        "paradas": listas, "pendientes": pendientes, "sin_programar": sin_programar,
        "puede_recorrer": not bloqueos, "bloqueos_recorrido": bloqueos,
        "orden_manual": bool(datos.get("orden")),
    }


def guardar_plan(ruta, usuario, body):
    """Guarda orden y carga personales con revisión; no afecta la solicitud."""
    if not isinstance(body, dict) or set(body) - {"fecha", "zona", "token", "orden", "cargadas"}:
        raise ValueError("Revisa los campos del plan")
    if body.get("fecha") != ruta["fecha"] or body.get("zona") != ruta["zona"] or body.get("token") != ruta["token"]:
        raise ValueError("La ruta cambió. Actualiza y revisa antes de guardar")
    orden, cargadas = body.get("orden"), body.get("cargadas")
    actuales = {p["id"]: p for p in ruta["paradas"]}
    for values in (orden, cargadas):
        if not isinstance(values, list) or len(values) > 1000 or any(not isinstance(v, str) for v in values) or len(values) != len(set(values)):
            raise ValueError("Revisa el orden y la lista de carga")
    if set(orden) != set(actuales) or not set(cargadas).issubset(actuales):
        raise ValueError("La lista de entregas cambió. Actualiza la ruta")
    if ruta["usuario"] != usuario:
        raise ValueError("La ruta corresponde a otra sesión")
    clave = _clave(usuario, ruta["fecha"], ruta["zona"])
    try:
        with store.SessionSesiones() as db:
            fila = db.query(store.PlanRuta).filter_by(clave=clave).with_for_update().first()
            revision = fila.revision if fila else 0
            if revision != ruta["revision"]:
                raise ValueError("Otra pestaña actualizó el plan. Recarga antes de guardar")
            anteriores = json.loads(fila.datos_json) if fila else {}
            # Mantener la carga de otras zonas al filtrar; un único plan por día.
            orden_anterior = anteriores.get("orden", [])
            restantes = [k for k in orden_anterior if k not in actuales]
            posicion = next((i for i, k in enumerate(orden_anterior) if k in actuales), len(restantes))
            posicion = min(posicion, len(restantes))
            orden_total = restantes[:posicion] + orden + restantes[posicion:]
            carga_total = {k: v for k, v in anteriores.get("cargadas", {}).items() if k not in actuales}
            carga_total.update({k: actuales[k]["huella"] for k in cargadas})
            nuevos = json.dumps({"orden": orden_total, "cargadas": carga_total})
            if fila:
                if db.query(store.PlanRuta).filter_by(id=fila.id, revision=revision).update({
                    "datos_json": nuevos, "revision": revision + 1, "actualizado_en": datetime.utcnow(),
                }, synchronize_session=False) != 1:
                    raise ValueError("La ruta cambió. Recarga antes de guardar")
            else:
                db.add(store.PlanRuta(clave=clave, usuario=usuario, fecha=ruta["fecha"], zona="todas", datos_json=nuevos))
            db.commit()
    except IntegrityError:
        raise ValueError("Otra pestaña actualizó el plan. Recarga antes de guardar") from None
