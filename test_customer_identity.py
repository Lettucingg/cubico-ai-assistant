"""Pruebas de identidad para clientes personales y agencias."""

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai import orchestrator
from app.db.database import Base
from app.db.models import Agencia, ClienteCBC, Factura, Pago, Paquete
from app.db.session_store import Sesion
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
    agencia = Agencia(
        codigo="SFE",
        nombre="Socios Freight Express",
        email="agencia@cubico.test",
        activo=True,
    )
    agencia_inactiva = Agencia(
        codigo="OFF4",
        nombre="Agencia Inactiva",
        email="agencia-inactiva@cubico.test",
        activo=False,
    )
    db.add_all([activo, inactivo, agencia, agencia_inactiva])
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
        tracking="TRACK-AGENCIA",
        tipo_cliente="agencia",
        agencia_id=agencia.id,
        estado_cargo="notificado",
    ))
    db.add(Factura(
        codigo="FAC-AGENCIA",
        tipo_cliente="agencia",
        agencia_id=agencia.id,
        total=35,
        estado="pendiente",
    ))
    db.add(Paquete(
        tracking="TRACK-AGENCIA-INACTIVA",
        tipo_cliente="agencia",
        agencia_id=agencia_inactiva.id,
        estado_cargo="notificado",
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
    return fabrica


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


def test_agencia_verifica_con_su_codigo_sin_pedir_cbc(tmp_path, monkeypatch):
    _crear_clientes(tmp_path, monkeypatch)

    resultado = clientes.verificar_identidad_cliente(
        " sfe ", " AGENCIA@cubico.test "
    )

    assert resultado["verificado"] is True
    assert resultado["tipo_cliente"] == "agencia"
    assert resultado["codigo_cliente"] == "SFE"
    assert resultado["nombre_completo"] == "Socios Freight Express"


def test_agencia_consulta_sus_paquetes_y_facturas(tmp_path, monkeypatch):
    _crear_clientes(tmp_path, monkeypatch)

    resultado_paquetes = paquetes.consultar_paquetes_por_codigo("sfe")
    resultado_facturas = facturas.consultar_facturas_por_codigo("SFE")

    assert resultado_paquetes["tipo_cliente"] == "agencia"
    assert resultado_paquetes["paquetes"][0]["tracking"] == "TRACK-AGENCIA"
    assert resultado_facturas["tipo_cliente"] == "agencia"
    assert resultado_facturas["saldo_pendiente_total"] == 35


def test_agencia_inactiva_no_verifica_ni_expone_datos(tmp_path, monkeypatch):
    _crear_clientes(tmp_path, monkeypatch)

    assert clientes.verificar_identidad_cliente(
        "OFF4", "agencia-inactiva@cubico.test"
    ) == {"verificado": False}
    assert clientes.verificar_correo_registrado("agencia-inactiva@cubico.test") == {
        "registrado": False
    }
    assert paquetes.consultar_paquetes_por_codigo("OFF4")["encontrado"] is False


def test_registra_pago_de_agencia_con_propietario_correcto(tmp_path, monkeypatch):
    fabrica = _crear_clientes(tmp_path, monkeypatch)

    resultado = facturas.registrar_pago_factura_desde_panel(
        "SFE",
        "FAC-AGENCIA",
        35,
        "yappy",
        "REF-AGENCIA-1",
    )

    db = fabrica()
    pago = db.query(Pago).filter(Pago.referencia == "REF-AGENCIA-1").one()
    agencia = db.query(Agencia).filter(Agencia.codigo == "SFE").one()
    assert resultado["estado_factura"] == "pagado"
    assert pago.tipo_cliente == "agencia"
    assert pago.agencia_id == agencia.id
    assert pago.cliente_cbc_id is None
    db.close()


def test_sesion_recuerda_el_tipo_de_identidad_verificada():
    assert "tipo_cliente_verificado" in Sesion.__table__.columns


def test_bruno_pide_codigo_de_persona_o_agencia_en_vez_de_solo_cbc():
    bloque_identidad = orchestrator.SYSTEM_PROMPT.split(
        "VERIFICACIÓN DE IDENTIDAD", 1
    )[1].split("TRACKING", 1)[0]
    herramienta = next(
        item
        for item in orchestrator.HERRAMIENTAS
        if item["name"] == "verificar_identidad_cliente"
    )

    assert "código propio si es una agencia" in bloque_identidad
    assert "código de cliente o agencia" in bloque_identidad
    assert "persona o agencia" in herramienta["description"]
    assert "por ejemplo SFE" in (
        herramienta["input_schema"]["properties"]["codigo_cliente"]["description"]
    )


def test_herramienta_de_bruno_guarda_la_sesion_como_agencia(monkeypatch):
    cambios = []
    respuestas = iter(
        [
            SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        name="verificar_identidad_cliente",
                        input={
                            "codigo_cliente": "sfe",
                            "email": "agencia@cubico.test",
                        },
                        id="tool-agencia",
                    )
                ],
                usage=None,
            ),
            SimpleNamespace(
                stop_reason="end_turn",
                content=[
                    SimpleNamespace(
                        type="text",
                        text="Listo, ya pude verificar la agencia.",
                    )
                ],
                usage=None,
            ),
        ]
    )
    monkeypatch.setattr(
        orchestrator,
        "verificar_identidad_cliente",
        lambda codigo, email: {
            "verificado": True,
            "codigo_cliente": "SFE",
            "tipo_cliente": "agencia",
            "nombre_completo": "Socios Freight Express",
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "actualizar_sesion",
        lambda telefono, **datos: cambios.append((telefono, datos)),
    )
    monkeypatch.setattr(
        orchestrator,
        "obtener_oportunidad_comercial_abierta",
        lambda telefono: None,
    )
    monkeypatch.setattr(
        orchestrator.cliente_claude.messages,
        "create",
        lambda **kwargs: next(respuestas),
    )

    respuesta = orchestrator.generar_respuesta(
        "Quiero consultar los paquetes de mi agencia.",
        "50760000001",
    )

    assert respuesta == "Listo, ya pude verificar la agencia."
    assert cambios == [
        (
            "50760000001",
            {
                "estado": "verificado",
                "codigo_cliente_verificado": "SFE",
                "tipo_cliente_verificado": "agencia",
            },
        )
    ]
