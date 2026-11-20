"""Confirmación operativa con registro y cierre en una sola transacción."""
import hashlib
import json
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import text
from app.db import session_store as store


def token_entrega(sesion, tipo):
    datos = [getattr(sesion, 'id', None), sesion.telefono, sesion.codigo_cliente_verificado,
             getattr(sesion, 'tipo_cliente_verificado', None), tipo,
             sesion.paquetes_a_domicilio if tipo == 'domicilio' else sesion.paquetes_a_retirar,
             sesion.direccion_domicilio if tipo == 'domicilio' else 'Sucursal Cúbico',
             bool(sesion.solicitud_domicilio_pendiente), bool(sesion.aviso_retiro_pendiente),
             bool(sesion.entregado), bool(sesion.paquetes_preparados), bool(sesion.domicilio_coordinado),
             str(getattr(sesion, 'solicitud_actualizada_en', None))]
    return hashlib.sha256(json.dumps(datos, ensure_ascii=False).encode()).hexdigest()


def serializar(fila):
    return dict(json.loads(fila.datos_json), id=fila.id, tipo=fila.tipo,
                telefono=fila.telefono, fecha=fila.fecha_local,
                confirmado_en=fila.confirmado_en.isoformat()+'Z', confirmado_por=fila.confirmado_por)


def confirmar_entrega(telefono, tipo, token, usuario, verificar_pago, nombre, *, anterior_reportada=False):
    if tipo not in {'retiro', 'domicilio'} or not isinstance(token, str) or not re.fullmatch('[a-f0-9]{64}', token):
        raise ValueError('Actualiza la solicitud antes de marcar la entrega')
    with store.SessionSesiones() as db:
        if db.get_bind().dialect.name == 'sqlite':
            db.execute(text('BEGIN IMMEDIATE'))
        anterior = db.query(store.EntregaPanel).filter_by(token=token, telefono=telefono, tipo=tipo).first()
        if anterior:
            return serializar(anterior)
        sesion = db.query(store.Sesion).filter_by(telefono=telefono).with_for_update().first()
        if not sesion or token != token_entrega(sesion, tipo):
            raise ValueError('La solicitud cambió. Actualiza antes de marcar entregado')
        pendiente = sesion.solicitud_domicilio_pendiente if tipo == 'domicilio' else sesion.aviso_retiro_pendiente
        paquetes = sesion.paquetes_a_domicilio if tipo == 'domicilio' else sesion.paquetes_a_retirar
        if sesion.entregado or not pendiente or (not anterior_reportada and not str(paquetes or '').strip()):
            raise ValueError('No hay paquetes pendientes de entrega en esta solicitud')
        if not anterior_reportada:
            verificar_pago(sesion)
            if not sesion.paquetes_preparados:
                raise ValueError('Primero marca los paquetes como listos')
            if tipo == 'domicilio' and not sesion.domicilio_coordinado:
                raise ValueError('Primero coordina el domicilio')
        now = datetime.now(timezone.utc)
        registro = store.EntregaPanel(token=token, telefono=telefono, tipo=tipo,
            fecha_local=now.astimezone(ZoneInfo('America/Panama')).date().isoformat(),
            confirmado_en=now.replace(tzinfo=None), confirmado_por=usuario,
            datos_json=json.dumps({'nombre': nombre(sesion) or telefono,
                'codigo_cliente': sesion.codigo_cliente_verificado, 'paquetes': paquetes,
                'entrega_anterior_reportada': anterior_reportada,
                'direccion': sesion.direccion_domicilio if tipo == 'domicilio' else 'Sucursal Cúbico'}, ensure_ascii=False))
        db.add(registro)
        if tipo == 'domicilio': sesion.solicitud_domicilio_pendiente = False
        else: sesion.aviso_retiro_pendiente = False
        sesion.entregado = not (sesion.aviso_retiro_pendiente or sesion.solicitud_domicilio_pendiente)
        sesion.solicitud_actualizada_en = now.replace(tzinfo=None)
        db.commit()
        return serializar(registro)


def listar_entregas(fecha):
    if not isinstance(fecha, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', fecha):
        raise ValueError('Selecciona una fecha válida')
    try: date.fromisoformat(fecha)
    except ValueError: raise ValueError('Selecciona una fecha válida') from None
    with store.SessionSesiones() as db:
        filas = db.query(store.EntregaPanel).filter_by(fecha_local=fecha).order_by(store.EntregaPanel.confirmado_en.desc(), store.EntregaPanel.id.desc()).limit(201).all()
        return {'fecha': fecha, 'entregas': [serializar(f) for f in filas[:200]], 'hay_mas': len(filas)>200}
