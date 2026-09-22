"""Contratos básicos del panel para evitar regresiones visuales recientes."""

from pathlib import Path

from app.api.panel import (
    _anonimizar_texto_exportado,
    _crear_exportacion_conversacion,
    _detectar_mime_archivo,
    _nombre_archivo_seguro,
)
from app.core.config import settings


PANEL = Path("app/static/panel-nuevo-diseno.html")


def _html() -> str:
    return PANEL.read_text(encoding="utf-8")


def test_no_expone_creacion_manual_de_oportunidades():
    html = _html()
    assert 'id="nueva-oportunidad"' not in html
    assert 'id="modal-nueva-oportunidad"' not in html
    assert "apiPost('/panel/oportunidad'" not in html


def test_chat_muestra_fecha_completa_en_zona_horaria_de_panama():
    html = _html()
    assert "formatearFechaChat" in html
    assert "weekday:'long'" in html
    assert "year:'numeric'" in html
    assert "timeZone:'America/Panama'" in html


def test_adjuntos_separan_fotos_y_documentos():
    html = _html()
    assert 'id="attach-menu"' in html
    assert 'id="attach-image-input"' in html
    assert 'id="attach-pdf-input"' in html
    assert 'data-attach-kind="image"' in html
    assert 'data-attach-kind="document"' in html


def test_backend_valida_el_contenido_real_del_adjunto():
    assert _detectar_mime_archivo(b"%PDF-1.7\ncontenido") == "application/pdf"
    assert _detectar_mime_archivo(b"\x89PNG\r\n\x1a\ncontenido") == "image/png"
    assert _detectar_mime_archivo(b"\xff\xd8\xffcontenido") == "image/jpeg"
    assert _detectar_mime_archivo(b"esto no es un pdf") is None


def test_backend_limpia_el_nombre_del_adjunto():
    assert _nombre_archivo_seguro("../../propuesta.pdf", "archivo") == "propuesta.pdf"
    assert _nombre_archivo_seguro(r"C:\\temporal\\foto.png", "archivo") == "foto.png"


def test_plantillas_usan_los_idiomas_aprobados_en_meta():
    assert settings.WHATSAPP_TEMPLATE_SALUDO_NAME == "cubico_saludo"
    assert settings.WHATSAPP_TEMPLATE_SALUDO_LANGUAGE == "es_PA"
    assert settings.WHATSAPP_TEMPLATE_PROPUESTA_NAME == "cubico_propuesta"
    assert settings.WHATSAPP_TEMPLATE_PROPUESTA_LANGUAGE == "es"


def test_propuesta_pide_contacto_y_empresa_para_las_dos_variables_de_meta():
    html = _html()
    assert 'id="propuesta-contacto"' in html
    assert 'id="propuesta-empresa"' in html
    assert "form.append('nombre',nombre)" in html
    assert "form.append('empresa',empresa)" in html


def test_panel_permite_exportar_una_conversacion_anonimizada():
    html = _html()
    assert 'id="export-chat"' in html
    assert "/panel/conversacion/${encodeURIComponent(telActivo)}/exportar" in html


def test_exportacion_distingue_cliente_bruno_y_equipo():
    texto = _crear_exportacion_conversacion([
        {
            "role": "user",
            "content": "Hola, soy Arthur. Mi correo es arthur@example.com y mi teléfono 507 6000-1234.",
            "timestamp": "2026-09-21T17:30:00Z",
        },
        {
            "role": "assistant",
            "content": "Hola Arthur, ¿cómo te ayudo?",
            "timestamp": "2026-09-21T17:31:00Z",
        },
        {
            "role": "humano",
            "content": "Ya revisamos tu solicitud.",
            "timestamp": "2026-09-21T17:32:00Z",
            "estado_entrega": "delivered",
        },
    ], ["Arthur"])

    assert "21/09/2026 12:30 PM" in texto
    assert "Cliente:" in texto
    assert "Bruno:" in texto
    assert "Equipo de Cúbico:" in texto
    assert "Arthur" not in texto
    assert "arthur@example.com" not in texto
    assert "6000-1234" not in texto
    assert "Estado: delivered" in texto


def test_anonimizacion_oculta_enlaces_y_codigos_largos():
    texto = _anonimizar_texto_exportado(
        "Revisa https://cubico.com/cliente/123 y el tracking 1ZAC2780YW66858393."
    )
    assert "https://" not in texto
    assert "1ZAC2780YW66858393" not in texto
