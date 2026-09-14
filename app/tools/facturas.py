from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func

from app.db.database import SessionLocal
from app.db.models import ClienteCBC, Factura, Pago


def _dinero(valor) -> Decimal:
    return Decimal(str(valor or 0)).quantize(Decimal("0.01"))


def _saldo_factura(factura: Factura) -> Decimal:
    pagado = sum((_dinero(pago.monto) for pago in factura.pagos if not pago.anulado), Decimal("0.00"))
    return max(Decimal("0.00"), _dinero(factura.total) - pagado)


def consultar_facturas_por_codigo(codigo_cliente: str) -> dict:
    """
    Busca un cliente por su código CBC y devuelve sus facturas,
    incluyendo cuáles están pendientes de pago y el saldo total
    adeudado.

    Al igual que con los paquetes, esta función es la única fuente
    de verdad sobre facturas — Claude nunca debe inventar montos ni
    estados de pago.
    """
    db = SessionLocal()
    try:
        cliente = (
            db.query(ClienteCBC)
            .filter(ClienteCBC.codigo == codigo_cliente)
            .first()
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

            if factura.estado != "pagado":
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
            "cliente": f"{cliente.nombre} {cliente.apellido or ''}".strip(),
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
        cliente = (
            db.query(ClienteCBC)
            .filter(func.upper(ClienteCBC.codigo) == codigo_cliente.strip().upper())
            .first()
        )
        if cliente is None:
            raise ValueError("El cliente no existe en facturación")

        factura = (
            db.query(Factura)
            .filter(
                Factura.cliente_cbc_id == cliente.id,
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
            duplicado = (
                db.query(Pago)
                .filter(
                    Pago.cliente_cbc_id == cliente.id,
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
            tipo_cliente="cbc",
            cliente_cbc_id=cliente.id,
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
