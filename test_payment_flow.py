"""Pruebas aisladas del registro financiero usado por el panel."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import ClienteCBC, Factura, Pago, Paquete
import app.tools.facturas as facturas
import pytest


@pytest.mark.parametrize("metodo", [None, "otro", "", "tarjeta"])
def test_metodo_no_permitido_no_registra_pago(tmp_path, metodo):
    fabrica = _crear_escenario(tmp_path)
    with pytest.raises(ValueError, match="método de pago válido"):
        facturas.registrar_pago_factura_desde_panel(
            "CBC-TEST", "FAC-TEST", 10, metodo, "REF-INVALIDA"
        )
    with fabrica() as db:
        assert db.query(Pago).count() == 0
        assert db.query(Factura).one().estado == "pendiente"


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
    assert db.query(Pago).one().tipo_pago == "completo"
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
    assert db.query(Pago).one().tipo_pago == "parcial"
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


def test_pago_anterior_no_reduce_factura_nueva(tmp_path):
    fabrica = _crear_escenario(tmp_path, total=47.50)
    with fabrica() as db:
        cliente = db.query(ClienteCBC).one()
        anterior = Factura(codigo="FAC-ANTERIOR", tipo_cliente="cbc", cliente_cbc_id=cliente.id,
                           total=22.50, estado="pagado")
        db.add(anterior)
        db.flush()
        db.add(Pago(factura_id=anterior.id, cliente_cbc_id=cliente.id, tipo_cliente="cbc",
                    monto=22.50, metodo="yappy", tipo_pago="completo", referencia="PAGO-ANTERIOR", anulado=False))
        db.commit()
    datos = facturas.consultar_facturas_por_codigo("CBC-TEST")
    assert datos["saldo_pendiente_total"] == 47.50
    assert next(f for f in datos["facturas"] if f["codigo"] == "FAC-TEST")["saldo_pendiente"] == 47.50
    with pytest.raises(ValueError, match="ya fue registrado"):
        facturas.registrar_pago_factura_desde_panel("CBC-TEST", "FAC-TEST", 22.50, "yappy", "PAGO-ANTERIOR")
    assert facturas.consultar_facturas_por_codigo("CBC-TEST")["saldo_pendiente_total"] == 47.50


def _dos_facturas(tmp_path):
    fabrica = _crear_escenario(tmp_path, total=5.40)
    with fabrica() as db:
        cliente = db.query(ClienteCBC).one()
        db.add(Factura(codigo="FAC-OTRA", tipo_cliente="cbc", cliente_cbc_id=cliente.id,
                       total=8.10, estado="pendiente"))
        db.commit()
    return fabrica


def test_un_comprobante_cubre_dos_facturas_y_su_suma_no_se_duplica(tmp_path):
    fabrica = _dos_facturas(tmp_path)
    resultado = facturas.registrar_pago_distribuido_desde_panel("CBC-TEST", [
        {"factura_codigo": "FAC-TEST", "monto": "5.40"},
        {"factura_codigo": "FAC-OTRA", "monto": "8.10"},
    ], "13.50", "yappy", "NGUVE-TEST")
    assert resultado["monto_registrado"] == 13.50
    with fabrica() as db:
        assert sum(float(p.monto) for p in db.query(Pago).all()) == 13.50
        assert {f.estado for f in db.query(Factura).all()} == {"pagado"}
        assert db.query(Paquete).one().estado_pago == "pagado"
    with pytest.raises(ValueError, match="ya fue registrado"):
        facturas.registrar_pago_distribuido_desde_panel("CBC-TEST", [
            {"factura_codigo": "FAC-TEST", "monto": "5.40"},
            {"factura_codigo": "FAC-OTRA", "monto": "8.10"},
        ], "13.50", "yappy", "nguve-test")
    with fabrica() as db:
        assert db.query(Pago).count() == 2


def test_abono_distribuido_deja_saldo_correcto(tmp_path):
    fabrica = _dos_facturas(tmp_path)
    facturas.registrar_pago_distribuido_desde_panel("CBC-TEST", [
        {"factura_codigo": "FAC-TEST", "monto": "5.40"},
        {"factura_codigo": "FAC-OTRA", "monto": "4.60"},
    ], "10.00", "ach", "ABONO-TEST")
    assert facturas.consultar_facturas_por_codigo("CBC-TEST")["saldo_pendiente_total"] == 3.50
    with fabrica() as db:
        assert db.query(Factura).filter_by(codigo="FAC-OTRA").one().estado == "parcial"


@pytest.mark.parametrize("asignaciones,total", [
    ([{"factura_codigo": "FAC-TEST", "monto": "5.40"}], "13.50"),
    ([{"factura_codigo": "FAC-TEST", "monto": "5.40"}, {"factura_codigo": "FAC-TEST", "monto": "8.10"}], "13.50"),
    ([{"factura_codigo": "FAC-TEST", "monto": "5.40"}, {"factura_codigo": "FAC-OTRA", "monto": "9.10"}], "14.50"),
    ([{"factura_codigo": "FAC-TEST", "monto": "5.40"}, {"factura_codigo": "NO-EXISTE", "monto": "8.10"}], "13.50"),
    ([{"factura_codigo": "FAC-TEST", "monto": "NaN"}], "NaN"),
    ([{"factura_codigo": "FAC-TEST", "monto": "-1"}], "-1"),
])
def test_distribucion_invalida_no_aplica_ninguna_parte(tmp_path, asignaciones, total):
    fabrica = _dos_facturas(tmp_path)
    with pytest.raises(ValueError):
        facturas.registrar_pago_distribuido_desde_panel("CBC-TEST", asignaciones, total, "yappy", "INVALIDA")
    with fabrica() as db:
        assert db.query(Pago).count() == 0
        assert {f.estado for f in db.query(Factura).all()} == {"pendiente"}


def test_no_distribuye_a_factura_de_otro_cliente(tmp_path):
    fabrica = _dos_facturas(tmp_path)
    with fabrica() as db:
        otro = ClienteCBC(codigo="CBC-OTRO", nombre="Otro")
        db.add(otro)
        db.flush()
        db.query(Factura).filter_by(codigo="FAC-OTRA").one().cliente_cbc_id = otro.id
        db.commit()
    with pytest.raises(ValueError, match="no pertenece"):
        facturas.registrar_pago_distribuido_desde_panel("CBC-TEST", [
            {"factura_codigo": "FAC-TEST", "monto": "5.40"},
            {"factura_codigo": "FAC-OTRA", "monto": "8.10"},
        ], "13.50", "yappy", "OTRO-CLIENTE")
    with fabrica() as db:
        assert db.query(Pago).count() == 0


def test_no_redondea_importes_fraccionarios_ocultamente(tmp_path):
    fabrica = _dos_facturas(tmp_path)
    with pytest.raises(ValueError):
        facturas.registrar_pago_distribuido_desde_panel("CBC-TEST", [
            {"factura_codigo": "FAC-TEST", "monto": "1.005"},
        ], "1.005", "yappy", "FRACCION")
    with fabrica() as db:
        assert db.query(Pago).count() == 0
