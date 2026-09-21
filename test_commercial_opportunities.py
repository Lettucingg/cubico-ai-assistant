"""Pruebas del registro comercial y el comportamiento natural de Bruno."""

import asyncio

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.ai import orchestrator
from app.ai.orchestrator import HERRAMIENTAS, buscar_respuesta_fija
from app.api import panel
from app.api import whatsapp
from app.db import session_store


def _base_aislada(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'oportunidades.db'}")
    session_store.BaseSesiones.metadata.create_all(engine)
    fabrica = sessionmaker(bind=engine)
    monkeypatch.setattr(session_store, "SessionSesiones", fabrica)
    return fabrica


def test_actualiza_la_misma_oportunidad_sin_duplicarla(tmp_path, monkeypatch):
    _base_aislada(tmp_path, monkeypatch)

    primera = session_store.guardar_oportunidad_comercial(
        "50760000000",
        empresa="Arthur English Bookstore",
        mercancia="libros",
    )
    segunda = session_store.guardar_oportunidad_comercial(
        "50760000000",
        volumen_estimado="10 cajas por semana",
        modalidades="marítimo; aéreo solo si es competitivo",
    )

    oportunidades = session_store.listar_oportunidades_comerciales()
    assert primera["id"] == segunda["id"]
    assert len(oportunidades) == 1
    assert oportunidades[0]["empresa"] == "Arthur English Bookstore"
    assert oportunidades[0]["volumen_estimado"] == "10 cajas por semana"


def test_resumen_solamente_usa_datos_confirmados(tmp_path, monkeypatch):
    _base_aislada(tmp_path, monkeypatch)

    oportunidad = session_store.guardar_oportunidad_comercial(
        "50760000001",
        empresa="Arthur English Bookstore",
        necesidad="reducir el costo de importar libros",
        mercancia="libros",
        origen="Miami",
        proveedores_actuales="TLC y Portex",
        preferencia_entrega="entrega por la tarde con un día de aviso",
    )

    assert "Arthur English Bookstore" in oportunidad["resumen"]
    assert "TLC y Portex" in oportunidad["resumen"]
    assert "10 cajas" not in oportunidad["resumen"]
    assert "nombre de la persona de contacto" in oportunidad["informacion_pendiente"]


def test_cerrar_permite_un_ciclo_comercial_nuevo(tmp_path, monkeypatch):
    _base_aislada(tmp_path, monkeypatch)

    primera = session_store.guardar_oportunidad_comercial(
        "50760000002", empresa="Empresa Uno"
    )
    session_store.actualizar_oportunidad_comercial(
        primera["id"], estado="no_concretada", asignado_a="alexander"
    )
    segunda = session_store.guardar_oportunidad_comercial(
        "50760000002", empresa="Empresa Dos"
    )

    assert primera["id"] != segunda["id"]
    assert len(session_store.listar_oportunidades_comerciales()) == 2


def test_rechaza_estado_comercial_desconocido(tmp_path, monkeypatch):
    _base_aislada(tmp_path, monkeypatch)
    oportunidad = session_store.guardar_oportunidad_comercial(
        "50760000003", empresa="Empresa de Prueba"
    )

    try:
        session_store.actualizar_oportunidad_comercial(
            oportunidad["id"], estado="inventado"
        )
        assert False, "debió rechazar el estado desconocido"
    except ValueError as error:
        assert "inválido" in str(error)


def test_bruno_no_se_despide_por_un_agradecimiento():
    respuesta = buscar_respuesta_fija("Gracias!")
    assert respuesta
    assert "hasta luego" not in respuesta.lower()
    assert "cuídate" not in respuesta.lower()


def test_herramienta_comercial_esta_disponible():
    herramienta = next(
        item for item in HERRAMIENTAS
        if item["name"] == "registrar_oportunidad_comercial"
    )
    propiedades = herramienta["input_schema"]["properties"]
    assert "empresa" in propiedades
    assert "volumen_estimado" in propiedades
    assert herramienta["input_schema"]["additionalProperties"] is False


def test_trabajador_toma_oportunidad_sin_poder_robarla(monkeypatch):
    base = {
        "id": 7,
        "estado": "nueva",
        "asignado_a": None,
    }
    recibidos = {}
    monkeypatch.setattr(panel, "listar_oportunidades_comerciales", lambda: [base])
    monkeypatch.setattr(
        panel,
        "actualizar_oportunidad_comercial",
        lambda oportunidad_id, **datos: recibidos.update(datos) or {**base, **datos},
    )

    resultado = panel.modificar_oportunidad_panel(
        7,
        panel.OportunidadPayload(tomar=True),
        usuario="alexander",
    )
    assert resultado["estado"] == "en_revision"
    assert recibidos["asignado_a"] == "alexander"

    monkeypatch.setattr(
        panel,
        "listar_oportunidades_comerciales",
        lambda: [{**base, "asignado_a": "luis"}],
    )
    try:
        panel.modificar_oportunidad_panel(
            7,
            panel.OportunidadPayload(tomar=True),
            usuario="alexander",
        )
        assert False, "no debe permitir tomar el caso de otro operador"
    except HTTPException as error:
        assert error.status_code == 409


def test_conversacion_larga_recibe_los_datos_comerciales_guardados(monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        orchestrator,
        "obtener_oportunidad_comercial_abierta",
        lambda _telefono: {
            "empresa": "Arthur English Bookstore",
            "proveedores_actuales": "TLC y Portex",
            "volumen_estimado": "10 cajas por semana",
        },
    )
    monkeypatch.setattr(
        orchestrator.cliente_claude.messages,
        "create",
        lambda **argumentos: llamadas.append(argumentos) or SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="Perfecto, quedó anotado.")],
            usage=None,
        ),
    )

    respuesta = orchestrator.generar_respuesta(
        "La entrega sería por las tardes.",
        "50760000004",
        historial=[
            {"role": "user", "content": f"mensaje antiguo {indice}"}
            for indice in range(30)
        ],
    )

    texto_interno = llamadas[0]["messages"][-1]["content"]
    assert respuesta == "Perfecto, quedó anotado."
    assert "Arthur English Bookstore" in texto_interno
    assert "TLC y Portex" in texto_interno
    assert "No repitas preguntas ya contestadas" in texto_interno


def test_prompt_no_inventa_origen_ni_promete_propuesta_comercial():
    bloque = orchestrator.SYSTEM_PROMPT.split("TARIFAS EMPRESARIALES", 1)[1]
    bloque = bloque.split("PROTOCOLO DE CALIDAD", 1)[0]

    assert "No asumas el origen" in bloque
    assert "No prometas que alguien se comunicará" in bloque
    assert "ya dejé la información para que el equipo revise" in bloque
    assert "se va a comunicar contigo para darte una propuesta" not in bloque


def test_mensajes_del_mismo_cliente_se_procesan_en_orden(monkeypatch):
    activos = 0
    maximo_activos = 0
    orden = []

    async def procesamiento_falso(mensaje):
        nonlocal activos, maximo_activos
        activos += 1
        maximo_activos = max(maximo_activos, activos)
        orden.append(f"inicio-{mensaje['texto']}")
        await asyncio.sleep(0.02)
        orden.append(f"fin-{mensaje['texto']}")
        activos -= 1

    monkeypatch.setattr(
        whatsapp,
        "_procesar_mensaje_en_segundo_plano_sin_candado",
        procesamiento_falso,
    )
    whatsapp.candados_procesamiento.clear()

    async def ejecutar():
        await asyncio.gather(
            whatsapp.procesar_mensaje_en_segundo_plano(
                {"telefono": "50760000010", "texto": "uno"}
            ),
            whatsapp.procesar_mensaje_en_segundo_plano(
                {"telefono": "50760000010", "texto": "dos"}
            ),
        )

    asyncio.run(ejecutar())

    assert maximo_activos == 1
    assert orden == ["inicio-uno", "fin-uno", "inicio-dos", "fin-dos"]
