"""Contratos básicos del panel para evitar regresiones visuales recientes."""

from pathlib import Path

from app.api.panel import _detectar_mime_archivo, _nombre_archivo_seguro
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


def test_propuesta_se_puede_enviar_desde_cualquier_conversacion():
    html = _html()
    assert 'id="enviar-propuesta-chat"' in html
    assert "document.getElementById('enviar-propuesta-chat').disabled=!activo" in html
    assert "abrirModalPropuesta(telActivo,(conv&&conv.nombre)||'','')" in html


def test_perfil_distingue_agencia_de_cliente_personal():
    html = _html()
    assert "conv.tipo_cliente_verificado==='agencia'" in html
    assert "Agencia verificada" in html
    assert "Cliente verificado" in html
