from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func

from app.db.database import SessionLocal
from app.db.models import Factura, Pago
from app.tools.clientes import buscar_identidad_activa_por_codigo


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
        saldo_pendiente_total = 0.0

        for factura in cliente.facturas:
            total = _dinero(factura.total)
            saldo_factura = _saldo_factura(factura)

            if not _factura_esta_pagada(factura):
                saldo_pendiente_total += float(saldo_factura)

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
            "saldo_pendiente_total": round(saldo_pendiente_total, 2),
            "facturas": facturas,
        }

    finally:
        db.close()


def registrar_pago_factura_desde_panel(
    codigo_cliente: str,
    codigo_factura: str,
    monto: float,
    metodo: str | None,
    referencia: str | None,
    fecha_reportada: str | None = None,
) -> dict:
    """Registra una confirmación real y recalcula factura/paquetes atómicamente."""
    importe = _dinero(monto)
    if importe <= 0:
        raise ValueError("El comprobante no tiene un monto válido")

    db = SessionLocal()
    try:
        tipo_cliente, cliente, _ = buscar_identidad_activa_por_codigo(
            db, codigo_cliente
        )
        if cliente is None:
            raise ValueError("El cliente no existe en facturación")

        filtro_propietario_factura = (
            Factura.cliente_cbc_id == cliente.id
            if tipo_cliente == "cbc"
            else Factura.agencia_id == cliente.id
        )
        factura = (
            db.query(Factura)
            .filter(
                filtro_propietario_factura,
                func.upper(Factura.codigo) == codigo_factura.strip().upper(),
            )
            .with_for_update()
            .first()
        )
        if factura is None:
            raise ValueError("La factura seleccionada no pertenece al cliente")

        saldo_antes = _saldo_factura(factura)
        if saldo_antes <= 0:
            raise ValueError("La factura ya aparece pagada")
        if importe > saldo_antes:
            raise ValueError(
                f"El pago de ${float(importe):.2f} supera el saldo de ${float(saldo_antes):.2f}"
            )

        referencia_limpia = (referencia or "").strip()
        referencia_util = referencia_limpia.lower() not in {"", "no visible", "no especificado"}
        if referencia_util:
            filtro_propietario_pago = (
                Pago.cliente_cbc_id == cliente.id
                if tipo_cliente == "cbc"
                else Pago.agencia_id == cliente.id
            )
            duplicado = (
                db.query(Pago)
                .filter(
                    filtro_propietario_pago,
                    Pago.referencia == referencia_limpia,
                    Pago.anulado.isnot(True),
                )
                .first()
            )
            if duplicado:
                raise ValueError("Ese número de referencia ya fue registrado")

        fecha_pago = datetime.now(UTC).replace(tzinfo=None)
        if fecha_reportada:
            for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    fecha_pago = datetime.strptime(fecha_reportada.strip(), formato)
                    break
                except ValueError:
                    continue

        db.add(Pago(
            factura_id=factura.id,
            tipo_cliente=tipo_cliente,
            cliente_cbc_id=cliente.id if tipo_cliente == "cbc" else None,
            agencia_id=cliente.id if tipo_cliente == "agencia" else None,
            monto=importe,
            metodo=(metodo or "otro").strip().lower(),
            referencia=referencia_limpia if referencia_util else None,
            fecha_pago=fecha_pago,
            anulado=False,
            registrado_por=None,
        ))
        db.flush()

        saldo_despues = max(Decimal("0.00"), saldo_antes - importe)
        factura.estado = "pagado" if saldo_despues <= Decimal("0.01") else "parcial"
        if factura.estado == "pagado":
            for paquete in factura.paquetes:
                paquete.estado_pago = "pagado"
        db.commit()
        return {
            "factura": factura.codigo,
            "monto_registrado": float(importe),
            "saldo_anterior": float(saldo_antes),
            "saldo_restante": float(saldo_despues),
            "estado_factura": factura.estado,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
