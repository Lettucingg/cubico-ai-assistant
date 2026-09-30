import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services import daily_reports, push_notifications


def test_actividad_no_cuenta_notas_ni_notificaciones():
    from types import SimpleNamespace
    inicio = datetime(2026, 9, 24, 5)
    historial = [{"role": "assistant", "timestamp": "2026-09-24T12:00:00Z"},
                 {"role": "user", "timestamp": "2026-09-23T12:00:00Z"}]
    sesion = SimpleNamespace(obtener_historial=lambda: historial)
    assert not daily_reports._actividad_cliente_hoy(sesion, inicio)
    historial.append({"role": "user", "timestamp": "2026-09-24T12:00:00Z"})
    assert daily_reports._actividad_cliente_hoy(sesion, inicio)


def test_fecha_del_informe_usa_panama(monkeypatch):
    class Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            instante = datetime(2026, 9, 24, 3, 0, tzinfo=timezone.utc)
            return instante.astimezone(tz) if tz else instante.replace(tzinfo=None)
    monkeypatch.setattr(daily_reports, "datetime", Reloj)
    assert daily_reports._inicio_hoy_utc() == datetime(2026, 9, 23, 5, 0)


def test_informe_no_envia_sin_usuarios(monkeypatch):
    from app import scheduler
    monkeypatch.setattr(scheduler.settings, "CUBICO_TEAM_REPORT_USERS_JSON", "[]")
    monkeypatch.setattr(scheduler, "datos_informe", lambda: pytest.fail("No hay destino"))
    asyncio.run(scheduler.enviar_ping_diario())


def test_informe_usa_push_sin_post_whatsapp(monkeypatch):
    from app import scheduler
    monkeypatch.setattr(scheduler.settings, "CUBICO_TEAM_REPORT_USERS_JSON", '["alexander","luis"]')
    monkeypatch.setattr(scheduler, "datos_informe", lambda: {
        "fecha": "24/09/2026", "humanos_pendientes": 2, "pagos_pendientes": 1,
        "retiros_pendientes": 0, "domicilios_pendientes": 3,
        "conversaciones_hoy": 12, "oportunidades_nuevas": 1, "costo_hoy": .12,
    })
    solicitudes, avisos, guardados = [], [], []
    def manejador(request):
        solicitudes.append(request)
        return httpx.Response(200)
    original = httpx.AsyncClient
    monkeypatch.setattr(scheduler.httpx, "AsyncClient", lambda **k: original(transport=httpx.MockTransport(manejador)))
    def guardar(tipo, contenido):
        guardados.append(contenido)
        return {"id": 1, "tipo": tipo}, True
    async def avisar(informe, usuarios):
        avisos.append((informe, usuarios))
        return {"enviadas": 2, "configurado": True}
    monkeypatch.setattr(scheduler, "guardar_informe", guardar)
    monkeypatch.setattr(scheduler, "notificar_informe_push", avisar)
    asyncio.run(scheduler.resumen_fin_dia())
    assert len(solicitudes) == 1 and solicitudes[0].method == "GET"
    assert avisos[0][1] == {"alexander", "luis"}
    assert "12 conversaciones" in guardados[0]


def test_push_informes_no_llega_a_otros_trabajadores(monkeypatch):
    suscripciones = [{"endpoint": u, "keys": {}, "usuario": u} for u in ["alexander", "luis", "teresa", "pepo"]]
    enviados = []
    monkeypatch.setattr(push_notifications, "push_configurado", lambda: True)
    monkeypatch.setattr(push_notifications, "listar_suscripciones_push", lambda: suscripciones)
    monkeypatch.setattr(push_notifications, "webpush", lambda **k: enviados.append(k))
    resultado = asyncio.run(push_notifications.notificar_informe_push({"id": 7, "tipo": "mañana"}, {"alexander", "luis", "teresa"}))
    assert resultado["enviadas"] == 3
    assert {e["subscription_info"]["endpoint"] for e in enviados} == {"alexander", "luis", "teresa"}
    assert all(json.loads(e["data"])["url"] == "/admin?informe=7" for e in enviados)


def test_guardar_informe_persiste_y_no_duplica(tmp_path, monkeypatch):
    from app.db.session_store import InformeDiario
    engine = create_engine(f"sqlite:///{tmp_path / 'informes.db'}")
    InformeDiario.__table__.create(engine)
    monkeypatch.setattr(daily_reports, "SessionSesiones", sessionmaker(bind=engine))
    primero, nuevo = daily_reports.guardar_informe("mañana", "Pendientes de apertura")
    repetido, otro = daily_reports.guardar_informe("mañana", "No sobrescribir")
    cierre, nuevo_cierre = daily_reports.guardar_informe("cierre", "Resumen")
    assert nuevo and nuevo_cierre and not otro
    assert repetido == primero
    assert len(daily_reports.listar_informes()) == 2
    assert cierre["id"] != primero["id"]


def test_informes_exigen_usuario_autorizado(monkeypatch):
    from app.api import panel
    from fastapi import HTTPException
    monkeypatch.setattr(panel, "usuarios_informes", lambda: {"alexander", "luis", "teresa"})
    monkeypatch.setattr(panel, "listar_informes", lambda: [{"id": 1}])
    assert panel.informes_diarios_panel(usuario="luis") == [{"id": 1}]
    assert panel.informes_diarios_panel(usuario="teresa") == [{"id": 1}]
    with pytest.raises(HTTPException) as error:
        panel.informes_diarios_panel(usuario="pepo")
    assert error.value.status_code == 403
