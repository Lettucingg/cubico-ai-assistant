from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, text

from app.db.database import SessionLocal
from app.db.models import Factura, Pago
from app.tools.clientes import buscar_identidad_activa_por_codigo


def _referencia_pago(valor):
    return str(valor or "").strip().lstrip("#").strip().casefold()


def _dinero(valor) -> Decimal:
    return Decimal(str(valor or 0)).quantize(Decimal("0.01"))


def _factura_esta_pagada(factura: Factura) -> bool:
    return str(factura.estado or "").strip().lower() in {
        "pagado", "pagada", "paid", "completado", "completada",
    }


def _saldo_factura(factura: Factura) -> Decimal:
    # La página web puede marcar la factura como pagada sin crear una
    # fila en `pagos`. En ese caso el estado de facturación manda y no
    # debemos ofrecer registrar el mismo comprobante una segunda vez.
    if _factura_esta_pagada(factura):
        return Decimal("0.00")
    pagado = sum((_dinero(pago.monto) for pago in factura.pagos if not pago.anulado), Decimal("0.00"))
    return max(Decimal("0.00"), _dinero(factura.total) - pagado)


def consultar_facturas_por_codigo(codigo_cliente: str) -> dict:
    """
    Busca una persona o agencia por su código y devuelve sus facturas,
    incluyendo cuáles están pendientes de pago y el saldo total
    adeudado.

    Al igual que con los paquetes, esta función es la única fuente
    de verdad sobre facturas — Claude nunca debe inventar montos ni
    estados de pago.
    """
    db = SessionLocal()
    try:
        tipo_cliente, cliente, codigo_normalizado = buscar_identidad_activa_por_codigo(
            db, codigo_cliente
        )

        if cliente is None:
            return {
                "encontrado": False,
                "mensaje": f"No se encontró ningún cliente con el código {codigo_cliente}.",
            }

        facturas = []
        saldo_pendiente_total = Decimal("0.00")

        for factura in cliente.facturas:
            total = _dinero(factura.total)
            saldo_factura = _saldo_factura(factura)

            if not _factura_esta_pagada(factura):
                saldo_pendiente_total += saldo_factura

            facturas.append({
                "codigo": factura.codigo,
                "total": float(total),
                "estado": factura.estado,
                "saldo_pendiente": float(saldo_factura),
                "fecha_emision": (
                    factura.fecha_emision.strftime("%Y-%m-%d")
                    if factura.fecha_emision else None
                ),
                "paquetes": [
                    {
                        "tracking": paquete.tracking,
                        "peso": float(paquete.peso) if paquete.peso is not None else None,
                        "costo": float(paquete.costo) if paquete.costo is not None else None,
                        "estado_cargo": paquete.estado_cargo,
                        "estado_pago": paquete.estado_pago,
                    }
                    for paquete in factura.paquetes
                ],
            })

        return {
            "encontrado": True,
            "cliente": (
                f"{cliente.nombre} {getattr(cliente, 'apellido', '') or ''}".strip()
                if tipo_cliente == "cbc"
                else str(cliente.nombre).strip()
            ),
            "tipo_cliente": tipo_cliente,
            "codigo_cliente": codigo_normalizado,
            "cantidad_facturas": len(facturas),
            "saldo_pendiente_total": float(saldo_pendiente_total),
            "facturas": facturas,
        }

    finally:
        db.close()


def consultar_ultimo_pago_por_codigo(codigo_cliente: str) -> dict:
    """Consulta pagos reales del propietario; nunca usa la emisión de factura."""
    db = SessionLocal()
    try:
        tipo, cliente, codigo = buscar_identidad_activa_por_codigo(db, codigo_cliente)
        if cliente is None:
            return {"encontrado": False, "mensaje": "No se encontró el cliente verificado."}
        pagos = [p for p in cliente.pagos if not p.anulado]
        fechados = [p for p in pagos if p.fecha_pago is not None]
        if not fechados:
            return {"encontrado": True, "codigo_cliente": codigo, "ultimo_pago": None,
                    "fecha_disponible": False,
                    "mensaje": "No hay una fecha de pago registrada. Una factura pagada no permite deducir cuándo se pagó."}
        pago = max(fechados, key=lambda p: (p.fecha_pago, p.id))
        # Si hay movimientos sin fecha, no podemos ordenar todo el historial.
        incompleto = len(fechados) != len(pagos)
        return {"encontrado": True, "codigo_cliente": codigo, "tipo_cliente": tipo,
                "fecha_disponible": True, "historial_fechas_incompleto": incompleto,
                "ultimo_pago": {"fecha_pago": pago.fecha_pago.strftime("%Y-%m-%d"),
                                "monto": float(_dinero(pago.monto)), "metodo": pago.metodo,
                                "factura": pago.factura.codigo if pago.factura else None},
                "mensaje": "Último pago con fecha registrada; existen otros pagos sin fecha." if incompleto else "Último pago registrado, incluyendo abonos parciales."}
    finally:
        db.close()


def registrar_pago_factura_desde_panel(
    codigo_cliente: str, codigo_factura: str, monto: float,
    metodo: str | None, referencia: str | None, fecha_reportada: str | None = None,
) -> dict:
    resultado = registrar_pago_distribuido_desde_panel(
        codigo_cliente, [{"factura_codigo": codigo_factura, "monto": monto}],
        monto, metodo, referencia, fecha_reportada,
    )
    return resultado["distribuciones"][0]


def registrar_pago_distribuido_desde_panel(
    codigo_cliente: str, asignaciones: list, monto: float,
    metodo: str | None, referencia: str | None, fecha_reportada: str | None = None,
) -> dict:
    """Una confirmación bancaria, varias aplicaciones; todo o nada."""
    try:
        importe = _dinero(monto)
        if not importe.is_finite() or importe <= 0 or Decimal(str(monto)) != importe:
            raise ValueError
    except Exception:
        raise ValueError("El comprobante no tiene un monto válido") from None
    metodo_normalizado = (metodo or "").strip().lower()
    if metodo_normalizado not in {"yappy", "ach", "efectivo"}:
        raise ValueError("Selecciona un método de pago válido: Yappy, ACH o efectivo")
    if not isinstance(asignaciones, list) or not 1 <= len(asignaciones) <= 50:
        raise ValueError("Selecciona entre una y cincuenta facturas")
    aplicaciones = {}
    for item in asignaciones:
        if not isinstance(item, dict):
            raise ValueError("Distribución de pago inválida")
        codigo = str(item.get("factura_codigo") or "").strip().upper()
        try:
            valor = _dinero(item.get("monto"))
            if not valor.is_finite() or valor <= 0 or Decimal(str(item.get("monto"))) != valor:
                raise ValueError
        except Exception:
            raise ValueError("Cada importe debe ser mayor que cero") from None
        if not codigo or codigo in aplicaciones:
            raise ValueError("Cada factura debe seleccionarse una sola vez")
        aplicaciones[codigo] = valor
    if sum(aplicaciones.values(), Decimal("0.00")) != importe:
        raise ValueError("La suma asignada debe coincidir exactamente con el comprobante")
    referencia_limpia = (referencia or "").strip()
    referencia_util = _referencia_pago(referencia_limpia) not in {"", "no visible", "no especificado", "sin referencia", "no legible", "pendiente", "none", "null", "n/a", "s/r"}
    if metodo_normalizado in {"yappy", "ach"} and not referencia_util:
        raise ValueError("Falta la referencia bancaria legible. Revisa el ingreso antes de registrar el pago; no lo confirmes nuevamente")
    if len(aplicaciones) > 1 and not referencia_util:
        raise ValueError("Para distribuir el pago se necesita una referencia legible")
    db = SessionLocal()
    try:
        # SQLite ignora FOR UPDATE. Reclamar la escritura antes de consultar saldos.
        if db.get_bind().dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        tipo_cliente, cliente, _ = buscar_identidad_activa_por_codigo(db, codigo_cliente)
        if cliente is None:
            raise ValueError("El cliente no existe en facturación")
        # Serializa las aplicaciones del mismo cliente, incluso entre facturas.
        db.query(type(cliente)).filter_by(id=cliente.id).with_for_update().one()
        if referencia_util:
            propietario_pago = (Pago.cliente_cbc_id == cliente.id if tipo_cliente == "cbc"
                                else Pago.agencia_id == cliente.id)
            candidatos = db.query(Pago).filter(
                propietario_pago, Pago.anulado.isnot(True), Pago.referencia.isnot(None),
            ).all()
            duplicado = next((p for p in candidatos
                if _referencia_pago(p.referencia) == _referencia_pago(referencia_limpia)), None)
            if duplicado:
                raise ValueError("Ese número de referencia ya fue registrado; revisa su aplicación")
        propietario = (Factura.cliente_cbc_id == cliente.id if tipo_cliente == "cbc"
                       else Factura.agencia_id == cliente.id)
        facturas = db.query(Factura).filter(
            propietario, func.upper(Factura.codigo).in_(sorted(aplicaciones)),
        ).order_by(Factura.id).with_for_update().populate_existing().all()
        if len(facturas) != len(aplicaciones):
            raise ValueError("Una factura seleccionada no pertenece al cliente o ya no existe")
        fecha_pago = datetime.now(UTC).replace(tzinfo=None)
        if fecha_reportada:
            for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    fecha_pago = datetime.strptime(fecha_reportada.strip(), formato)
                    break
                except ValueError:
                    continue
        resultados = []
        for factura in facturas:
            valor = aplicaciones[factura.codigo.strip().upper()]
            db.expire(factura, ["pagos"])
            saldo_antes = _saldo_factura(factura)
            if saldo_antes <= 0:
                raise ValueError("La factura ya aparece pagada; recarga antes de confirmar")
            if valor > saldo_antes:
                raise ValueError(f"El pago de ${float(valor):.2f} supera el saldo de ${float(saldo_antes):.2f} en {factura.codigo}")
            db.add(Pago(
                factura_id=factura.id, tipo_cliente=tipo_cliente,
                cliente_cbc_id=cliente.id if tipo_cliente == "cbc" else None,
                agencia_id=cliente.id if tipo_cliente == "agencia" else None,
                monto=valor, metodo=metodo_normalizado,
                tipo_pago="completo" if valor == saldo_antes else "parcial",
                referencia=referencia_limpia if referencia_util else None,
                fecha_pago=fecha_pago, anulado=False, registrado_por=None,
            ))
            saldo_despues = saldo_antes - valor
            factura.estado = "pagado" if saldo_despues == 0 else "parcial"
            if factura.estado == "pagado":
                for paquete in factura.paquetes:
                    paquete.estado_pago = "pagado"
            resultados.append({"factura": factura.codigo, "monto_registrado": float(valor),
                               "saldo_anterior": float(saldo_antes), "saldo_restante": float(saldo_despues),
                               "estado_factura": factura.estado})
        db.commit()
        return {"monto_registrado": float(importe), "distribuciones": resultados}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
