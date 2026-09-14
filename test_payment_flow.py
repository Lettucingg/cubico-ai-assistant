"""Pruebas aisladas del registro financiero usado por el panel."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import ClienteCBC, Factura, Pago, Paquete
import app.tools.facturas as facturas


def _crear_escenario(tmp_path, total=10):
    engine = create_engine(f"sqlite:///{tmp_path / 'facturacion.db'}")
    Base.metadata.create_all(engine)
    fabrica = sessionmaker(bind=engine)
    facturas.SessionLocal = fabrica
    db = fabrica()
    cliente = ClienteCBC(codigo="CBC-TEST", nombre="Cliente", apellido="Prueba")
    db.add(cliente)
    db.flush()
    factura = Factura(
        codigo="FAC-TEST",
        tipo_cliente="cbc",
        cliente_cbc_id=cliente.id,
        total=total,
        estado="pendiente",
    )
    db.add(factura)
    db.flush()
    db.add(Paquete(
        tracking="TRACK-TEST",
        tipo_cliente="cbc",
        cliente_cbc_id=cliente.id,
        factura_id=factura.id,
        estado_pago="pendiente",
    ))
    db.commit()
    db.close()
    return fabrica


def test_pago_total_actualiza_factura_y_paquete(tmp_path):
    fabrica = _crear_escenario(tmp_path)
    resultado = facturas.registrar_pago_factura_desde_panel(
        "CBC-TEST", "FAC-TEST", 10, "Yappy", "REF-001", "14/09/2026"
    )
    assert resultado["saldo_restante"] == 0
    db = fabrica()
    assert db.query(Factura).one().estado == "pagado"
    assert db.query(Paquete).one().estado_pago == "pagado"
    assert float(db.query(Pago).one().monto) == 10
    db.close()


def test_pago_parcial_deja_saldo_y_paquete_pendiente(tmp_path):
    fabrica = _crear_escenario(tmp_path, total=15)
    resultado = facturas.registrar_pago_factura_desde_panel(
        "CBC-TEST", "FAC-TEST", 10, "ACH", "REF-002"
    )
    assert resultado["saldo_restante"] == 5
    db = fabrica()
    assert db.query(Factura).one().estado == "parcial"
    assert db.query(Paquete).one().estado_pago == "pendiente"
    db.close()


def test_no_permite_pago_superior_al_saldo(tmp_path):
    fabrica = _crear_escenario(tmp_path)
    try:
        facturas.registrar_pago_factura_desde_panel(
            "CBC-TEST", "FAC-TEST", 20, "Yappy", "REF-003"
        )
        assert False, "debió rechazar el pago superior"
    except ValueError as error:
        assert "supera el saldo" in str(error)
    db = fabrica()
    assert db.query(Pago).count() == 0
    db.close()


def test_respeta_factura_marcada_pagada_por_la_web(tmp_path):
    fabrica = _crear_escenario(tmp_path)
    db = fabrica()
    db.query(Factura).one().estado = "pagado"
    db.commit()
    db.close()

    consulta = facturas.consultar_facturas_por_codigo("CBC-TEST")

    assert consulta["saldo_pendiente_total"] == 0
    assert consulta["facturas"][0]["saldo_pendiente"] == 0
    try:
        facturas.registrar_pago_factura_desde_panel(
            "CBC-TEST", "FAC-TEST", 10, "Yappy", "REF-DUPLICADA"
        )
        assert False, "no debe duplicar un pago ya reflejado por la web"
    except ValueError as error:
        assert "ya aparece pagada" in str(error)
