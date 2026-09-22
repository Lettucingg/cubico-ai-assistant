"""Pruebas del contexto que Bruno recibe después de enviar plantillas."""

from app.ai.orchestrator import normalizar_historial_para_claude


def test_bruno_lee_el_texto_real_de_una_plantilla_nueva():
    historial = [
        {
            "role": "humano",
            "content": "[Plantilla enviada: saludo a Lucía]",
            "contexto_ia": (
                "El equipo de Cúbico envió al cliente una plantilla de "
                'WhatsApp con este mensaje: "Hola Lucía, ¿qué tal?"'
            ),
        }
    ]

    mensajes = normalizar_historial_para_claude(historial)

    assert mensajes == [
        {
            "role": "assistant",
            "content": (
                "El equipo de Cúbico envió al cliente una plantilla de "
                'WhatsApp con este mensaje: "Hola Lucía, ¿qué tal?"'
            ),
        }
    ]


def test_bruno_reconstruye_un_saludo_enviado_antes_de_la_mejora():
    mensajes = normalizar_historial_para_claude(
        [{"role": "humano", "content": "[Plantilla enviada: saludo a Luis]"}]
    )

    assert mensajes[0]["role"] == "assistant"
    assert '"Hola Luis, ¿qué tal?"' in mensajes[0]["content"]


def test_bruno_reconstruye_una_propuesta_enviada_antes_de_la_mejora():
    mensajes = normalizar_historial_para_claude(
        [
            {
                "role": "humano",
                "content": (
                    "[Plantilla enviada: propuesta para Arthur English Bookstore, "
                    "contacto equipo (Tarifas.pdf)]"
                ),
            }
        ]
    )

    contenido = mensajes[0]["content"]
    assert mensajes[0]["role"] == "assistant"
    assert 'documento PDF "Tarifas.pdf"' in contenido
    assert "Hola equipo" in contenido
    assert "Arthur English Bookstore" in contenido


def test_mensaje_normal_conserva_su_contenido():
    mensajes = normalizar_historial_para_claude(
        [{"role": "user", "content": "Sí, me parece bien la propuesta."}]
    )

    assert mensajes == [
        {"role": "user", "content": "Sí, me parece bien la propuesta."}
    ]
