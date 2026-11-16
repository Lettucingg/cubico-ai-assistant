"""Consulta de conciliación; no crea, anula ni mueve pagos."""
import argparse
import json
from app.db.database import SessionLocal
from app.db.models import Factura, Pago
from app.tools.facturas import _saldo_factura


def audit(invoice_code):
    with SessionLocal() as db:
        invoice = db.query(Factura).filter(Factura.codigo == invoice_code.strip()).first()
        if invoice is None:
            raise ValueError("No se encontró la factura")
        owner = (Pago.cliente_cbc_id == invoice.cliente_cbc_id
                 if invoice.cliente_cbc_id is not None
                 else Pago.agencia_id == invoice.agencia_id)
        if invoice.cliente_cbc_id is None and invoice.agencia_id is None:
            raise ValueError("La factura no tiene cliente asociado")
        payments = db.query(Pago).filter(owner).order_by(Pago.id.desc()).all()
        return {
            "solo_consulta": True,
            "factura": invoice.codigo,
            "total_factura": float(invoice.total or 0),
            "estado": invoice.estado,
            "saldo_actual": float(_saldo_factura(invoice)),
            "paquetes_factura": [p.tracking for p in invoice.paquetes],
            "pagos_cliente": [{
                "id": p.id, "factura": p.factura.codigo if p.factura else None,
                "monto": float(p.monto or 0), "referencia": p.referencia,
                "fecha": p.fecha_pago.isoformat() if p.fecha_pago else None,
                "anulado": bool(p.anulado),
            } for p in payments],
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factura", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.factura), ensure_ascii=False, indent=2))
    except ValueError as error:
        parser.exit(1, str(error) + "\n")
