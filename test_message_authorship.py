"""Evita confundir respuestas humanas, plantillas y respuestas de Bruno."""

import asyncio
from types import SimpleNamespace

from app.ai.orchestrator import normalizar_historial_para_claude
from app.api import panel, whatsapp


def test_contexto_conserva_mensaje_humano_sin_presentarlo_como_voz_de_bruno():
    mensajes = normalizar_historial_para_claude([
        {
            "role": "humano",
            "content": "Yo siempre te voy a querer.",
            "autor_tipo": "humano",
            "operador": "alexander",
        }
    ])

    assert mensajes[0]["role"] == "assistant"
    assert "enviado por alexander, no por Bruno" in mensajes[0]["content"]
    assert "no imites automáticamente su tono" in mensajes[0]["content"]


def test_respuesta_iniciada_en_panel_se_registra_como_humana_asistida(monkeypatch):
    registrado = {}
    sesion = SimpleNamespace(
        obtener_historial=lambda: [{"role": "user", "content": "Ayúdame"}],
    )

    monkeypatch.setattr(panel, "obtener_sesion_existente", lambda _telefono: sesion)
    monkeypatch.setattr(panel, "_validar_operador_conversacion", lambda *_args, **_kwargs: sesion)
    monkeypatch.setattr(panel, "redactar_respuesta_de_asesor", lambda _original, borrador: borrador)

    async def enviar(*_args, **_kwargs):
        return SimpleNamespace(is_success=True)

    monkeypatch.setattr(panel, "enviar_respuesta_natural", enviar)
    monkeypatch.setattr(panel, "extraer_id_mensaje_meta", lambda _respuesta: "wamid-1")
    monkeypatch.setattr(panel, "actualizar_sesion", lambda *_args, **_kwargs: None)

    def guardar(telefono, rol, contenido, **metadatos):
        registrado.update(
            telefono=telefono,
            rol=rol,
            contenido=contenido,
            **metadatos,
        )

    monkeypatch.setattr(panel, "agregar_al_historial", guardar)

    asyncio.run(
        panel.responder_cliente(
            "50760000000",
            {"mensaje": "Lo revisamos enseguida."},
            usuario="alexander",
        )
    )

    assert registrado["rol"] == "humano"
    assert registrado["autor_tipo"] == "humano"
    assert registrado["operador"] == "alexander"
    assert registrado["modo_envio"] == "asistido_bruno"


def test_bruno_cancela_envio_si_humano_toma_control_mientras_escribe(monkeypatch):
    enviados = []

    async def sin_espera(_segundos):
        return None

    async def enviar(*args, **kwargs):
        enviados.append((args, kwargs))
        return SimpleNamespace(is_success=True)

    monkeypatch.setattr(whatsapp.asyncio, "sleep", sin_espera)
    monkeypatch.setattr(
        whatsapp,
        "obtener_sesion_existente",
        lambda _telefono: SimpleNamespace(atencion_humana_directa=True),
    )
    monkeypatch.setattr(whatsapp, "enviar_mensaje_whatsapp", enviar)

    resultado = asyncio.run(
        whatsapp.enviar_respuesta_natural(
            "50760000000",
            "Respuesta que ya no debe salir",
            "",
            detener_si_control_humano=True,
        )
    )

    assert resultado is None
    assert enviados == []


def test_detector_de_limite_corta_frases_de_acoso_o_no_contacto():
    assert whatsapp.respuesta_para_limite_del_cliente("No me escribas más")
    assert whatsapp.respuesta_para_limite_del_cliente("Me estás acosando")
    assert whatsapp.respuesta_para_limite_del_cliente("Necesito una cotización") is None


def test_limite_del_cliente_no_llega_a_claude(monkeypatch):
    sesion = SimpleNamespace(telefono="50760000000", atencion_humana_directa=False)
    guardados = []
    cambios = {}
    enviados = []

    monkeypatch.setattr(whatsapp, "obtener_o_crear_sesion", lambda _telefono: sesion)
    monkeypatch.setattr(
        whatsapp,
        "generar_respuesta",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("No debe llamar a Claude")),
    )
    monkeypatch.setattr(
        whatsapp,
        "agregar_al_historial",
        lambda telefono, rol, contenido, **meta: guardados.append((telefono, rol, contenido, meta)),
    )
    monkeypatch.setattr(
        whatsapp,
        "actualizar_sesion",
        lambda telefono, **valores: cambios.update(telefono=telefono, **valores),
    )

    async def notificar(*_args, **_kwargs):
        return None

    async def enviar(telefono, texto):
        enviados.append((telefono, texto))
        return SimpleNamespace(is_success=True)

    monkeypatch.setattr(whatsapp, "notificar_equipo_escalamiento", notificar)
    monkeypatch.setattr(whatsapp, "enviar_mensaje_whatsapp", enviar)
    monkeypatch.setattr(whatsapp, "extraer_id_mensaje_meta", lambda _respuesta: "wamid-stop")

    import asyncio

    asyncio.run(
        whatsapp._procesar_mensaje_en_segundo_plano_sin_candado(
            {
                "telefono": "50760000000",
                "texto": "Déjame tranquilo, no me escribas",
                "tipo": "text",
                "message_id": "wamid-in",
            }
        )
    )

    assert cambios["motivo_escalamiento"] == "Cliente pidió detener la conversación"
    assert len(enviados) == 1
    assert [item[1] for item in guardados] == ["user", "assistant"]
