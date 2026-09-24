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


def test_informe_no_envia_sin_destinatarios_y_plantilla(monkeypatch):
    from app import scheduler

    monkeypatch.setattr(scheduler.settings, "CUBICO_TEAM_REPORT_NUMBERS_JSON", "[]")
    monkeypatch.setattr(scheduler.settings, "CUBICO_TEAM_REPORT_TEMPLATE", "")
    monkeypatch.setattr(scheduler, "datos_informe", lambda: pytest.fail("No debe consultar datos sin destino"))
    asyncio.run(scheduler.enviar_ping_diario())


def test_envio_individual_continua_si_meta_rechaza_un_destinatario(monkeypatch):
    import httpx
    from app import scheduler

    monkeypatch.setattr(scheduler.settings, "CUBICO_TEAM_REPORT_NUMBERS_JSON", '["11111111111","22222222222","11111111111"]')
    monkeypatch.setattr(scheduler.settings, "CUBICO_TEAM_REPORT_TEMPLATE", "informe_equipo")
    monkeypatch.setattr(scheduler, "datos_informe", lambda: {
        "fecha": "24/09/2026", "humanos_pendientes": 2, "pagos_pendientes": 1,
        "retiros_pendientes": 0, "domicilios_pendientes": 3,
        "conversaciones_hoy": 12, "oportunidades_nuevas": 1, "costo_hoy": .12,
    })
    solicitudes = []

    def manejador(request):
        solicitudes.append(request)
        return httpx.Response(200 if request.method == "GET" or b'22222222222' in request.read() else 400, text="plantilla no aprobada")

    transporte = httpx.MockTransport(manejador)
    cliente_original = httpx.AsyncClient
    monkeypatch.setattr(scheduler.httpx, "AsyncClient", lambda **kwargs: cliente_original(transport=transporte))
    asyncio.run(scheduler.resumen_fin_dia())
    assert len(solicitudes) == 3
    assert b'"to":"11111111111"' in solicitudes[1].read()
    assert b'"to":"22222222222"' in solicitudes[2].read()
    assert all(b'"recipient_type":"group"' not in solicitud.read() for solicitud in solicitudes)


def test_informe_no_envia_si_algun_destinatario_es_invalido(monkeypatch):
    from app import scheduler

    monkeypatch.setattr(scheduler.settings, "CUBICO_TEAM_REPORT_NUMBERS_JSON", '["11111111111","numero_invalido"]')
    monkeypatch.setattr(scheduler.settings, "CUBICO_TEAM_REPORT_TEMPLATE", "informe_equipo")
    monkeypatch.setattr(scheduler, "datos_informe", lambda: pytest.fail("No debe consultar datos con destinos inválidos"))
    asyncio.run(scheduler.enviar_ping_diario())
