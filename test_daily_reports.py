import asyncio
from datetime import datetime, timezone

import pytest

from app.services import daily_reports


def test_fecha_del_informe_usa_panama(monkeypatch):
    class Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            instante = datetime(2026, 9, 24, 3, 0, tzinfo=timezone.utc)
            return instante.astimezone(tz) if tz else instante.replace(tzinfo=None)

    monkeypatch.setattr(daily_reports, "datetime", Reloj)
    assert daily_reports._inicio_hoy_utc() == datetime(2026, 9, 23, 5, 0)


def test_informe_no_envia_sin_grupo_y_plantilla(monkeypatch):
    from app import scheduler

    monkeypatch.setattr(scheduler.settings, "CUBICO_TEAM_REPORT_GROUP_ID", "")
    monkeypatch.setattr(scheduler.settings, "CUBICO_TEAM_REPORT_TEMPLATE", "")
    monkeypatch.setattr(scheduler, "datos_informe", lambda: pytest.fail("No debe consultar datos sin destino"))
    asyncio.run(scheduler.enviar_ping_diario())


def test_envio_al_grupo_rechazo_meta_no_se_considera_entregado(monkeypatch):
    import httpx
    from app import scheduler

    monkeypatch.setattr(scheduler.settings, "CUBICO_TEAM_REPORT_GROUP_ID", "grupo-valido")
    monkeypatch.setattr(scheduler.settings, "CUBICO_TEAM_REPORT_TEMPLATE", "informe_equipo")
    monkeypatch.setattr(scheduler, "datos_informe", lambda: {
        "fecha": "24/09/2026", "humanos_pendientes": 2, "pagos_pendientes": 1,
        "retiros_pendientes": 0, "domicilios_pendientes": 3,
        "conversaciones_hoy": 12, "oportunidades_nuevas": 1, "costo_hoy": .12,
    })
    solicitudes = []

    def manejador(request):
        solicitudes.append(request)
        return httpx.Response(200 if request.method == "GET" else 400, text="plantilla no aprobada")

    transporte = httpx.MockTransport(manejador)
    cliente_original = httpx.AsyncClient
    monkeypatch.setattr(scheduler.httpx, "AsyncClient", lambda **kwargs: cliente_original(transport=transporte))
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(scheduler.resumen_fin_dia())
    assert len(solicitudes) == 2
    assert solicitudes[1].read().find(b'"recipient_type":"group"') != -1
    assert b'"to":"grupo-valido"' in solicitudes[1].read()
