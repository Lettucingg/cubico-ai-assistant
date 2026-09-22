"""Pruebas de memoria para la plantilla de carga disponible."""

import httpx

from app.api import notificaciones


def _carga() -> notificaciones.CargaLlegadaBody:
    return notificaciones.CargaLlegadaBody(
        telefono="50760000000",
        nombre="Alexander",
        codigo="CBC-0018",
        tracking="1ZPRUEBA123",
        factura="FAC-2048",
        monto="27.50",
        paquetes="PKG-1, PKG-2",
    )


def test_contexto_de_carga_contiene_todos_los_datos_para_bruno():
    contexto = notificaciones._contexto_ia_carga_llegada(_carga())

    assert "disponible para retiro" in contexto
    assert "CBC-0018" in contexto
    assert "1ZPRUEBA123" in contexto
    assert "FAC-2048" in contexto
    assert "USD 27.50" in contexto
    assert "PKG-1, PKG-2" in contexto
    assert "no actúes como si fuera una conversación nueva" in contexto


def test_notificacion_crea_sesion_y_guarda_contexto_completo(monkeypatch):
    sesiones_creadas = []
    mensajes_guardados = []
    monkeypatch.setattr(
        notificaciones,
        "obtener_o_crear_sesion",
        lambda telefono: sesiones_creadas.append(telefono),
    )
    monkeypatch.setattr(
        notificaciones,
        "agregar_al_historial",
        lambda *args, **kwargs: mensajes_guardados.append((args, kwargs)),
    )
    respuesta = httpx.Response(
        200,
        json={"messages": [{"id": "wamid-carga-1"}]},
    )

    notificaciones._registrar_carga_llegada_en_historial(_carga(), respuesta)

    assert sesiones_creadas == ["50760000000"]
    assert len(mensajes_guardados) == 1
    args, kwargs = mensajes_guardados[0]
    assert args[:2] == ("50760000000", "assistant")
    assert kwargs["tipo"] == "template"
    assert kwargs["whatsapp_message_id"] == "wamid-carga-1"
    assert kwargs["estado_entrega"] == "accepted"
    assert "1ZPRUEBA123" in kwargs["contexto_ia"]
    assert "FAC-2048" in kwargs["contexto_ia"]
