"""Vigila trackings consultados: fecha conocida y ubicación explícita, sin IA."""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from app.db.session_store import TrackingVigilado, SessionSesiones

log = logging.getLogger(__name__)


def fecha_miami(resultado, ahora):
    if resultado.get('ubicacion') != 'Miami':
        return None
    fechas = []
    for registro in resultado.get('registros_proveedor', []):
        try:
            fecha = datetime.fromisoformat(registro['fecha_ingreso_proveedor'].replace('Z', '+00:00'))
            # Una fecha sin zona no basta para decidir cuántas horas han pasado.
            if fecha.tzinfo is None:
                return None
            if fecha.tzinfo is not None:
                fecha = fecha.astimezone(timezone.utc).replace(tzinfo=None)
                if fecha > ahora:
                    return None
                fechas.append(fecha)
        except (KeyError, ValueError, TypeError, AttributeError):
            return None
    # Si hay varios registros, usamos el ingreso más reciente para no exagerar la demora.
    return max(fechas) if fechas else None


def observar(tracking, telefono, resultado, ahora=None):
    if resultado.get('error') or not resultado.get('encontrado'):
        return []  # Una consulta fallida no confirma llegada ni resuelve la advertencia.
    ahora = ahora or datetime.now(timezone.utc).replace(tzinfo=None)
    ingreso = fecha_miami(resultado, ahora)
    demora = bool(ingreso and ahora - ingreso >= timedelta(days=6))
    malid = bool(resultado.get('identificacion_incorrecta'))
    nuevas = []
    with SessionSesiones() as db:
        row = db.get(TrackingVigilado, (tracking, telefono))
        if row is None:
            row = TrackingVigilado(tracking=tracking, telefono=telefono)
            db.add(row)
        if demora and not row.push_demora:
            nuevas.append('demora_miami')
        if malid and not row.push_malid:
            nuevas.append('malid')
        if not demora:
            row.push_demora = False
        if not malid:
            row.push_malid = False
        row.demora, row.mal_identificado, row.ingreso_miami = demora, malid, ingreso
        row.actualizado_en = ahora
        db.commit()
    return [a for a in listar_alertas(ahora) if a['tracking'] == tracking and a['telefono'] == telefono and a['kind'] in nuevas]


def listar_alertas(ahora=None):
    ahora = ahora or datetime.now(timezone.utc).replace(tzinfo=None)
    import json
    rows = []
    with SessionSesiones() as db:
        for row in db.query(TrackingVigilado).all():
            for kind, active in [('malid', row.mal_identificado), ('demora_miami', row.demora)]:
                if not active:
                    continue
                dias = max(0, (ahora - row.ingreso_miami).days) if row.ingreso_miami else None
                rows.append({
                    'kind': kind, 'tracking': row.tracking, 'telefono': row.telefono,
                    'clave': json.dumps([kind, row.tracking, row.telefono], separators=(',', ':')),
                    'titulo': ('Paquete mal identificado' if kind == 'malid' else 'Paquete con demora en Miami') + ' · ' + row.tracking,
                    'descripcion': ('Necesita revisión para asociarlo correctamente al cliente.' if kind == 'malid' else f'{dias} días desde el ingreso registrado en Miami. Revisar el envío; no hay otra ubicación confirmada en esta consulta.') + ' Cliente: ' + row.telefono,
                    'target': {'view': 'chats', 'tel': row.telefono}, 'warn': True,
                })
    return rows


async def notificar_nuevas(alertas):
    from app.services.push_notifications import notificar_alerta_push
    from app.services.alert_archive import listar_archivadas
    ocultas = {a['clave'] for a in await asyncio.to_thread(listar_archivadas)}
    for alerta in alertas:
        if alerta['clave'] in ocultas:
            continue
        campo = 'push_malid' if alerta['kind'] == 'malid' else 'push_demora'
        # Reclama el evento en la BD antes del envío: dos revisiones no lo repiten.
        with SessionSesiones() as db:
            changed = db.query(TrackingVigilado).filter_by(tracking=alerta['tracking'], telefono=alerta['telefono'], **{campo: False, 'mal_identificado' if alerta['kind'] == 'malid' else 'demora': True}).update({campo: True})
            db.commit()
        if changed:
            await notificar_alerta_push(alerta['titulo'], alerta['descripcion'], alerta['telefono'], alerta['clave'])


async def revisar_trackings():
    from app.tools.ptyfreight import consultar_tracking, _cache_tracking
    with SessionSesiones() as db:
        pendientes = [(r.tracking, r.telefono) for r in db.query(TrackingVigilado).all()]
    resultados = {}
    for tracking, telefono in pendientes:
        try:
            if tracking not in resultados:
                _cache_tracking.pop(tracking, None)
                resultados[tracking] = await asyncio.to_thread(consultar_tracking, tracking)
            nuevas = await asyncio.to_thread(observar, tracking, telefono, resultados[tracking])
            await notificar_nuevas([a for a in nuevas if a['kind'] == 'demora_miami'])
        except Exception:
            log.exception('No se pudo revisar un tracking vigilado')
