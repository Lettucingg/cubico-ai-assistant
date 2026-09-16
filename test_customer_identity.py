"""Pruebas de normalización y bloqueo de cuentas CBC inactivas."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import ClienteCBC, Factura, Paquete
from app.tools import clientes, facturas, paquetes


def _crear_clientes(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'clientes.db'}")
    Base.metadata.create_all(engine)
    fabrica = sessionmaker(bind=engine)
    for modulo in (clientes, facturas, paquetes):
        monkeypatch.setattr(modulo, "SessionLocal", fabrica)

    db = fabrica()
    activo = ClienteCBC(
        codigo="CBC-0018",
        nombre="Alexander",
        apellido="Prueba",
        email="cliente@cubico.test",
        activo=True,
    )
    inactivo = ClienteCBC(
        codigo="CBC-0099",
        nombre="Cuenta",
        apellido="Inactiva",
        email="inactivo@cubico.test",
        activo=False,
    )
    db.add_all([activo, inactivo])
    db.flush()
    db.add(Paquete(
        tracking="TRACK-ACTIVO",
        tipo_cliente="cbc",
        cliente_cbc_id=activo.id,
        estado_cargo="notificado",
    ))
    db.add(Factura(
        codigo="FAC-ACTIVA",
        tipo_cliente="cbc",
        cliente_cbc_id=activo.id,
        total=12,
        estado="pendiente",
    ))
    db.add(Paquete(
        tracking="TRACK-INACTIVO",
        tipo_cliente="cbc",
        cliente_cbc_id=inactivo.id,
        estado_cargo="notificado",
    ))
    db.add(Factura(
        codigo="FAC-INACTIVA",
        tipo_cliente="cbc",
        cliente_cbc_id=inactivo.id,
        total=20,
        estado="pendiente",
    ))
    db.commit()
    db.close()


def test_normaliza_codigo_cbc_con_variaciones():
    assert clientes.normalizar_codigo_cbc("cbc0018") == "CBC-0018"
    assert clientes.normalizar_codigo_cbc(" CBC_0018 ") == "CBC-0018"
    assert clientes.normalizar_codigo_cbc("CBC-0018") == "CBC-0018"


def test_verifica_cliente_sin_exigir_el_guion(tmp_path, monkeypatch):
    _crear_clientes(tmp_path, monkeypatch)

    assert clientes.verificar_cliente("cbc0018", " CLIENTE@cubico.test ")


def test_consultas_usan_la_misma_normalizacion(tmp_path, monkeypatch):
    _crear_clientes(tmp_path, monkeypatch)

    resultado_paquetes = paquetes.consultar_paquetes_por_codigo("CBC0018")
    resultado_facturas = facturas.consultar_facturas_por_codigo("cbc_0018")

    assert resultado_paquetes["encontrado"] is True
    assert resultado_paquetes["paquetes"][0]["tracking"] == "TRACK-ACTIVO"
    assert resultado_facturas["encontrado"] is True
    assert resultado_facturas["saldo_pendiente_total"] == 12


def test_cuenta_inactiva_no_verifica_ni_expone_datos(tmp_path, monkeypatch):
    _crear_clientes(tmp_path, monkeypatch)

    assert not clientes.verificar_cliente("CBC0099", "inactivo@cubico.test")
    assert clientes.verificar_correo_registrado("inactivo@cubico.test") == {
        "registrado": False
    }
    assert paquetes.consultar_paquetes_por_codigo("CBC0099")["encontrado"] is False
    assert facturas.consultar_facturas_por_codigo("CBC-0099")["encontrado"] is False
