from app.db.database import SessionLocal
from app.db.models import ClienteCBC


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
            total = float(factura.total) if factura.total else 0.0

            total_pagado = sum(
                float(pago.monto) for pago in factura.pagos if not pago.anulado
            )
            saldo_factura = total - total_pagado

            if factura.estado != "pagado":
                saldo_pendiente_total += saldo_factura

            facturas.append({
                "codigo": factura.codigo,
                "total": total,
                "estado": factura.estado,
                "saldo_pendiente": round(saldo_factura, 2),
                "fecha_emision": (
                    factura.fecha_emision.strftime("%Y-%m-%d")
                    if factura.fecha_emision else None
                ),
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