"""La fecha del último pago debe venir de movimientos reales del propietario."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import ClienteCBC, Agencia, Factura, Pago
from app.tools import facturas

@pytest.fixture
def escenario(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'pagos.db'}")
    Base.metadata.create_all(engine)
    fabrica = sessionmaker(bind=engine)
    monkeypatch.setattr(facturas, 'SessionLocal', fabrica)
    with fabrica() as db:
        cliente = ClienteCBC(codigo='CBC-0001', nombre='Cliente', activo=True)
        agencia = Agencia(codigo='AG1', nombre='Agencia', activo=True)
        db.add_all([cliente, agencia]); db.flush()
        db.add_all([
            Factura(codigo='FAC1', tipo_cliente='cbc', cliente_cbc_id=cliente.id,
                    total=30, estado='parcial', fecha_emision=datetime(2026,9,9)),
            Factura(codigo='FAC2', tipo_cliente='agencia', agencia_id=agencia.id,
                    total=20, estado='pagado', fecha_emision=datetime(2026,9,29)),
        ])
        db.commit()
    return fabrica

def agregar(fabrica, fecha, monto=5, anulado=False, factura='FAC1'):
    with fabrica() as db:
        f = db.query(Factura).filter_by(codigo=factura).one()
        db.add(Pago(factura_id=f.id, tipo_cliente=f.tipo_cliente, cliente_cbc_id=f.cliente_cbc_id,
                    agencia_id=f.agencia_id, fecha_pago=fecha, monto=monto, anulado=anulado,
                    metodo='yappy', tipo_pago='parcial'))
        db.commit()

def test_ultimo_abono_no_es_emision_y_excluye_anulado(escenario):
    agregar(escenario, datetime(2026,9,12), 5)
    agregar(escenario, datetime(2026,9,25), 7)
    agregar(escenario, datetime(2026,9,30), 18, anulado=True)
    r = facturas.consultar_ultimo_pago_por_codigo('CBC-0001')
    assert r['ultimo_pago']['fecha_pago'] == '2026-09-25'
    assert r['ultimo_pago']['monto'] == 7
    assert facturas.consultar_facturas_por_codigo('CBC-0001')['saldo_pendiente_total'] == 18

def test_factura_pagada_sin_movimientos_no_inventa_fecha(escenario):
    r = facturas.consultar_ultimo_pago_por_codigo('AG1')
    assert r['encontrado'] and not r['fecha_disponible']
    assert r['ultimo_pago'] is None

def test_fecha_faltante_no_se_presenta_como_historial_completo(escenario):
    agregar(escenario, datetime(2026,9,25))
    agregar(escenario, None)
    r = facturas.consultar_ultimo_pago_por_codigo('CBC-0001')
    assert r['historial_fechas_incompleto']

def test_agencia_consulta_solo_sus_pagos(escenario):
    agregar(escenario, datetime(2026,9,30), 5)
    agregar(escenario, datetime(2026,9,20), 20, factura='FAC2')
    r = facturas.consultar_ultimo_pago_por_codigo('AG1')
    assert r['ultimo_pago']['fecha_pago'] == '2026-09-20'
    assert r['ultimo_pago']['factura'] == 'FAC2'

def test_codigo_inexistente(escenario):
    assert not facturas.consultar_ultimo_pago_por_codigo('CBC-9999')['encontrado']
