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


def test_medios_expirados_no_muestran_error_global_del_servidor():
    html = _html()
    assert "notificarErrores=true" in html
    assert "r.status>=500&&creds&&notificarErrores" in html
    assert "audio.dataset.mediaId)}`,false)" in html
    assert "img.dataset.chatMediaId)}`,false)" in html
    assert "encodeURIComponent(s.telefono),false)" in html
    assert "Imagen no disponible; puede haber expirado en WhatsApp" in html


def test_flujo_de_pago_explica_cada_paso_al_operador():
    html = _html()
    assert "Pasos para completar el caso" in html
    assert "Primero compara el comprobante con la factura" in html
    assert "1. Revisar comprobante y registrar pago" in html
    assert "2. Confirmar paquetes listos" in html
    assert "4. Confirmar entrega al cliente" in html
    assert "Pago registrado; el saldo de facturación fue actualizado" in html
    assert "Comprobante revisado; no se registró un pago duplicado" in html



def test_panel_permite_exportar_una_conversacion_anonimizada():
    html = _html()
    assert 'id="export-chat"' in html
    assert "/panel/conversacion/${encodeURIComponent(telActivo)}/exportar" in html
    assert "revísalo antes de compartirlo" in html


def test_exportacion_distingue_cliente_bruno_y_equipo():
    texto = _crear_exportacion_conversacion([
        {
            "role": "user",
            "content": (
                "Hola, soy PersonaDePrueba. Mi correo es prueba@example.com "
                "y mi teléfono 000 0000-0000."
            ),
            "timestamp": "2026-09-21T17:30:00Z",
        },
        {
            "role": "assistant",
            "content": "Hola PersonaDePrueba, ¿cómo te ayudo?",
            "timestamp": "2026-09-21T17:31:00Z",
            "autor_tipo": "bruno",
        },
        {
            "role": "humano",
            "content": "Ya revisamos tu solicitud.",
            "timestamp": "2026-09-21T17:32:00Z",
            "estado_entrega": "delivered",
            "autor_tipo": "humano",
            "operador": "operador_prueba",
            "modo_envio": "asistido_bruno",
        },
    ], ["PersonaDePrueba"])

    assert "21/09/2026 12:30 PM" in texto
    assert "Cliente:" in texto
    assert "Bruno:" in texto
    assert "Equipo de Cúbico — operador_prueba (redacción asistida por Bruno):" in texto
    assert "PersonaDePrueba" not in texto
    assert "prueba@example.com" not in texto
    assert "0000-0000" not in texto
    assert "Estado: delivered" in texto


def test_exportacion_no_atribuye_a_bruno_respuestas_antiguas_ambiguas():
    texto = _crear_exportacion_conversacion([
        {
            "role": "assistant",
            "content": "Mensaje histórico",
            "timestamp": "2026-09-21T17:31:00Z",
        },
    ])

    assert "Respuesta saliente (origen antiguo no registrado):" in texto
    assert "Bruno: Mensaje histórico" not in texto


def test_anonimizacion_oculta_enlaces_facturas_y_codigos_largos():
    texto = _anonimizar_texto_exportado(
        "Revisa https://example.com/cliente/demo, la factura FAC-00000 "
        "y el tracking PRUEBA1234567890."
    )
    assert "https://" not in texto
    assert "FAC-00000" not in texto
    assert "PRUEBA1234567890" not in texto



def test_acciones_secundarias_no_saturan_la_cabecera_del_chat():
    html = _html()
    assert 'id="chat-actions-toggle"' in html
    assert 'id="chat-actions-menu"' in html
    assert 'id="reactivar-chat" data-chat-action' in html
    assert 'id="enviar-propuesta-chat" data-chat-action' in html
    assert 'id="export-chat" data-chat-action' in html
    assert "cerrarMenuAccionesChat" in html


def test_panel_muestra_quien_envio_cada_respuesta():
    html = _html()
    assert "etiquetaAutorMensaje" in html
    assert "Equipo · " in html
    assert "m.operador" in html
    assert "asistido por Bruno" in html
    assert "Salida anterior · origen sin registrar" in html


def test_chat_tiene_desplazamiento_visible_y_botones_de_inicio_y_final():
    html = _html()
    assert "overflow-y:scroll" in html
    assert "touch-action:pan-y" in html
    assert 'id="chat-scroll-top"' in html
    assert 'id="chat-scroll-bottom"' in html
    assert "actualizarControlesScroll" in html
    assert "messagesEl.scrollTo({top:0" in html
    assert "messagesEl.scrollTo({top:messagesEl.scrollHeight" in html


def test_panel_recomienda_un_siguiente_paso_al_operador():
    html = _html()
    assert 'id="next-step-card"' in html
    assert "actualizarSiguientePaso" in html
    assert "1. Verificar al cliente" in html
    assert "1. Revisar el pago" in html
    assert "Continuar el domicilio" in html
    assert "Continuar el retiro" in html


def test_acciones_operativas_son_accesibles_desde_celular():
    html = _html()
    assert 'id="mobile-customer-toggle"' in html
    assert "👤 Cliente y acciones" in html
    assert 'id="customer-panel"' in html
    assert 'id="customer-close"' in html
    assert "customer.mobile-open" in html
    assert "abrirPanelCliente" in html
    assert "cerrarPanelCliente" in html


def test_resumen_ofrece_accesos_directos_con_el_filtro_correcto():
    html = _html()
    assert 'data-summary-view="chats" data-chat-filter="humano"' in html
    assert 'data-summary-view="packages" data-package-filter="all"' in html
    assert 'data-summary-view="costs"' in html
    assert 'data-package-filter="pickup"' in html
    assert 'data-package-filter="delivery"' in html
    assert 'data-package-filter="payment"' in html
    assert 'data-package-filter="ready"' in html
    assert "abrirAccesoDirecto" in html


def test_indicadores_operativos_y_comerciales_son_filtros_tocables():
    html = _html()
    assert 'data-package-filter-link="pickup"' in html
    assert 'data-package-filter-link="payment"' in html
    assert 'data-opportunity-filter-link="new"' in html
    assert 'data-opportunity-filter-link="review"' in html
    assert 'data-opportunity-filter-link="sent"' in html
    assert 'data-opportunity-filter-link="won"' in html
    assert "aplicarFiltroSolicitud" in html
    assert "aplicarFiltroOportunidad" in html
    assert "scrollIntoView({behavior:'smooth',block:'start'})" in html
