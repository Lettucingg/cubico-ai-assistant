"""Ficha de domicilio: preferencias del cliente y programación interna separadas."""
import hashlib
import json
import re
from datetime import date, datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from sqlalchemy.exc import IntegrityError
from app.db import session_store as store

ZONAS = {"por_definir": (), "centro": (0, 2), "este": (1, 3), "otra": ()}
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
CAMPOS = {
    "direccion": 1000, "barrio": 120, "zona": 30, "ubicacion_url": 1000,
    "referencias": 1000, "dia_solicitado": 80, "fecha_solicitada": 10,
    "horario_solicitado": 200, "fecha_confirmada": 10,
    "hora_desde": 5, "hora_hasta": 5, "prioridad": 20, "motivo_prioridad": 250,
}
CAMPOS_CLIENTE = {"barrio", "zona", "ubicacion_url", "referencias",
                  "dia_solicitado", "fecha_solicitada", "horario_solicitado"}


def hoy():
    return datetime.now(ZoneInfo("America/Panama")).date()


def clave_caso(sesion):
    paquetes = sorted({p.strip().upper() for p in re.split(r"[,;\n]+", str(sesion.paquetes_a_domicilio or "")) if p.strip()})
    base = [sesion.telefono, sesion.codigo_cliente_verificado or "",
            getattr(sesion, "tipo_cliente_verificado", None) or "", paquetes]
    return hashlib.sha256(json.dumps(base, ensure_ascii=False).encode()).hexdigest()


def token_caso(sesion, revision):
    base = [clave_caso(sesion), revision, sesion.direccion_domicilio or "",
            bool(sesion.solicitud_domicilio_pendiente), bool(sesion.entregado),
            bool(sesion.paquetes_preparados), bool(sesion.domicilio_coordinado)]
    return hashlib.sha256(json.dumps(base).encode()).hexdigest()


def ubicacion_segura(url):
    if not isinstance(url, str) or len(url) > 1000:
        return False
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        if host in {"google.com", "www.google.com"}:
            return parsed.path.startswith("/maps")
        if host == "goo.gl":
            return parsed.path.startswith("/maps")
        return host in {"maps.app.goo.gl", "maps.google.com", "maps.apple.com",
                        "waze.com", "www.waze.com", "ul.waze.com"}
    except ValueError:
        return False


def validar_datos(datos):
    if not isinstance(datos, dict) or set(datos) - set(CAMPOS):
        raise ValueError("La ficha contiene campos no admitidos")
    limpios = {}
    for campo, valor in datos.items():
        if not isinstance(valor, str) or len(valor.strip()) > CAMPOS[campo]:
            raise ValueError("Revisa el campo " + campo)
        limpios[campo] = valor.strip()
    if "prioridad" in limpios and limpios["prioridad"] not in {"normal", "alta"}:
        raise ValueError("Selecciona una prioridad válida")
    if "zona" in limpios and limpios["zona"] not in ZONAS:
        raise ValueError("Selecciona una zona válida")
    if limpios.get("ubicacion_url") and not ubicacion_segura(limpios["ubicacion_url"]):
        raise ValueError("Usa un enlace HTTPS de Google Maps, Apple Maps o Waze; también puedes dejarlo vacío")
    for campo in ("fecha_solicitada", "fecha_confirmada"):
        if limpios.get(campo):
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", limpios[campo]):
                    raise ValueError
                date.fromisoformat(limpios[campo])
            except ValueError:
                raise ValueError("Revisa la fecha en formato AAAA-MM-DD") from None
    for campo in ("hora_desde", "hora_hasta"):
        if limpios.get(campo) and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", limpios[campo]):
            raise ValueError("Revisa el horario en formato HH:MM")
    return limpios


def faltantes(datos):
    errores = []
    if not datos.get("direccion"):
        errores.append("dirección")
    if datos.get("zona", "por_definir") == "por_definir":
        errores.append("zona")
    fecha = datos.get("fecha_confirmada")
    if not fecha:
        errores.append("fecha confirmada por el equipo")
    elif date.fromisoformat(fecha) < hoy():
        errores.append("reprogramar la fecha vencida")
    elif date.fromisoformat(fecha).weekday() >= 5:
        errores.append("programar de lunes a viernes")
    desde, hasta = datos.get("hora_desde"), datos.get("hora_hasta")
    if bool(desde) != bool(hasta) or (desde and hasta and desde > hasta):
        errores.append("revisar el intervalo de horas")
    return errores


def ubicacion_en_chat(sesion):
    for item in reversed(getattr(sesion, "obtener_historial", lambda: [])()):
        if item.get("role") != "user":
            continue
        pin = item.get("ubicacion") or {}
        lat, lon = pin.get("latitude"), pin.get("longitude")
        if (isinstance(lat, (int, float)) and not isinstance(lat, bool)
            and isinstance(lon, (int, float)) and not isinstance(lon, bool)
            and -90 <= lat <= 90 and -180 <= lon <= 180):
            return {"url": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}",
                    "timestamp": item.get("timestamp"), "tipo": "pin"}
        for url in re.findall(r"https://[^\s<>]+", str(item.get("content") or "")):
            url = url.rstrip(".,);]")
            if ubicacion_segura(url):
                return {"url": url, "timestamp": item.get("timestamp"), "tipo": "enlace"}
    return None


def _datos(fila, sesion):
    base = {campo: "" for campo in CAMPOS}
    base.update({"direccion": sesion.direccion_domicilio or "", "zona": "por_definir", "prioridad": "normal"})
    if fila:
        base.update(json.loads(fila.datos_json or "{}"))
    base["direccion"] = sesion.direccion_domicilio or ""
    return base


def _serializar(sesion, fila):
    datos = _datos(fila, sesion)
    errores = faltantes(datos)
    if fila and json.loads(fila.datos_json or "{}").get("direccion") != datos["direccion"]:
        errores.append("revisar cambio de dirección")
    revision = fila.revision if fila else 0
    return dict(datos, clave=clave_caso(sesion), revision=revision,
                token=token_caso(sesion, revision), ubicacion_compartida=ubicacion_en_chat(sesion),
                dias_preferentes=[DIAS[d] for d in ZONAS.get(datos["zona"], ())],
                faltantes=errores, listo_para_coordinar=not errores,
                actualizado_por=fila.actualizado_por if fila else None,
                actualizado_en=fila.actualizado_en.isoformat() + "Z" if fila else None)


def obtener_ficha(sesion):
    with store.SessionSesiones() as db:
        fila = db.query(store.FichaDomicilio).filter_by(clave=clave_caso(sesion)).first()
        return _serializar(sesion, fila)


def _exigir_caso(sesion):
    if sesion is None or not sesion.solicitud_domicilio_pendiente or sesion.entregado:
        raise ValueError("La solicitud de domicilio cambió o ya se cerró; recarga el caso")
    if not sesion.codigo_cliente_verificado or not sesion.paquetes_a_domicilio:
        raise ValueError("Verifica el cliente y los paquetes antes de guardar la ficha")


def _sesion_actual(db, sesion):
    query = db.query(store.Sesion).filter_by(id=sesion.id)
    for campo in ("codigo_cliente_verificado", "tipo_cliente_verificado", "direccion_domicilio",
                  "paquetes_a_domicilio", "solicitud_domicilio_pendiente", "entregado",
                  "paquetes_preparados", "domicilio_coordinado"):
        columna = getattr(store.Sesion, campo)
        valor = getattr(sesion, campo)
        query = query.filter(columna.is_(None) if valor is None else columna == valor)
    return query


def _guardar(db, sesion, fila, datos, usuario):
    ahora = datetime.utcnow()
    revision = fila.revision if fila else 0
    eventos = json.loads(fila.eventos_json or "[]") if fila else []
    eventos.append({"revision": revision + 1, "usuario": usuario,
                    "fecha": ahora.isoformat() + "Z", "datos": datos})
    cambios = dict(revision=revision + 1, datos_json=json.dumps(datos, ensure_ascii=False),
                   eventos_json=json.dumps(eventos, ensure_ascii=False),
                   actualizado_por=usuario, actualizado_en=ahora)
    if fila is None:
        fila = store.FichaDomicilio(clave=clave_caso(sesion), telefono=sesion.telefono,
            codigo_cliente=sesion.codigo_cliente_verificado, paquetes=sesion.paquetes_a_domicilio,
            **cambios)
        db.add(fila)
        db.flush()
    else:
        actualizadas = db.query(store.FichaDomicilio).filter_by(id=fila.id, revision=revision).update(cambios, synchronize_session=False)
        if actualizadas != 1:
            raise ValueError("Otra persona actualizó la ficha; recarga antes de guardar")
        db.refresh(fila)
    if _sesion_actual(db, sesion).update({
        "direccion_domicilio": datos["direccion"], "domicilio_coordinado": False,
        "solicitud_actualizada_en": ahora,
    }, synchronize_session=False) != 1:
        raise ValueError("La solicitud cambió mientras guardabas; recarga el caso")
    db.refresh(sesion)
    return fila


def guardar_ficha(telefono, datos, token, usuario):
    limpios = validar_datos(datos)
    db = store.SessionSesiones()
    try:
        sesion = db.query(store.Sesion).filter_by(telefono=telefono).with_for_update().first()
        _exigir_caso(sesion)
        fila = db.query(store.FichaDomicilio).filter_by(clave=clave_caso(sesion)).with_for_update().first()
        revision = fila.revision if fila else 0
        if not token or token != token_caso(sesion, revision):
            raise ValueError("El caso o la ficha cambió; recarga antes de guardar. No se aplicaron tus cambios")
        nuevos = dict(_datos(fila, sesion), **limpios)
        validar_datos(nuevos)
        if fila and nuevos == json.loads(fila.datos_json or "{}"):
            return _serializar(sesion, fila)
        fila = _guardar(db, sesion, fila, nuevos, usuario)
        resultado = _serializar(sesion, fila)
        db.commit()
        return resultado
    except IntegrityError:
        db.rollback()
        raise ValueError("Otra persona actualizó la ficha; recarga antes de guardar") from None
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def guardar_preferencias_cliente(telefono, preferencias):
    if not isinstance(preferencias, dict) or set(preferencias) - CAMPOS_CLIENTE:
        raise ValueError("Solo se pueden capturar preferencias solicitadas por el cliente")
    limpios = validar_datos(preferencias)
    with store.SessionSesiones() as db:
        sesion = db.query(store.Sesion).filter_by(telefono=telefono).with_for_update().first()
        _exigir_caso(sesion)
        fila = db.query(store.FichaDomicilio).filter_by(clave=clave_caso(sesion)).with_for_update().first()
        datos = dict(_datos(fila, sesion), **limpios)
        # La dirección vigente proviene de la solicitud recién registrada.
        datos["direccion"] = sesion.direccion_domicilio or datos["direccion"]
        if fila and datos != json.loads(fila.datos_json or "{}"):
            datos.update(fecha_confirmada="", hora_desde="", hora_hasta="")
        if fila and datos == json.loads(fila.datos_json or "{}"):
            return _serializar(sesion, fila)
        fila = _guardar(db, sesion, fila, datos, "Bruno · solicitud del cliente")
        resultado = _serializar(sesion, fila)
        db.commit()
        return resultado


def coordinar_ficha(telefono, token):
    with store.SessionSesiones() as db:
        sesion = db.query(store.Sesion).filter_by(telefono=telefono).with_for_update().first()
        _exigir_caso(sesion)
        fila = db.query(store.FichaDomicilio).filter_by(clave=clave_caso(sesion)).with_for_update().first()
        if not fila or token != token_caso(sesion, fila.revision):
            raise ValueError("Guarda y revisa la ficha actual antes de coordinar el domicilio")
        if not sesion.paquetes_preparados:
            raise ValueError("Primero marca los paquetes como listos")
        errores = _serializar(sesion, fila)["faltantes"]
        if errores:
            raise ValueError("Falta " + ", ".join(errores))
        # Reclamar la revisión evita coordinar una ficha que cambió en paralelo.
        if db.query(store.FichaDomicilio).filter_by(id=fila.id, revision=fila.revision).update(
            {"revision": fila.revision}, synchronize_session=False
        ) != 1:
            raise ValueError("La ficha cambió; revisa la programación")
        if _sesion_actual(db, sesion).update({
            "domicilio_coordinado": True, "solicitud_actualizada_en": datetime.utcnow(),
        }, synchronize_session=False) != 1:
            raise ValueError("La solicitud cambió; recarga el caso")
        db.commit()
