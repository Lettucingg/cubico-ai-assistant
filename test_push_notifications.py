import asyncio

from app.db.session_store import (
    eliminar_suscripcion_push,
    guardar_suscripcion_push,
    listar_suscripciones_push,
)
from app.services import push_notifications


def _suscripcion(endpoint: str) -> dict:
    return {
        "endpoint": endpoint,
        "keys": {"p256dh": "clave-publica-dispositivo", "auth": "secreto-dispositivo"},
    }


def test_suscripcion_push_persiste_y_se_elimina():
    endpoint = "https://push.example.test/dispositivo-prueba"
    eliminar_suscripcion_push(endpoint)
    guardar_suscripcion_push("tester", _suscripcion(endpoint))

    guardadas = listar_suscripciones_push()
    registro = next(s for s in guardadas if s["endpoint"] == endpoint)
    assert registro["usuario"] == "tester"
    assert registro["keys"]["auth"] == "secreto-dispositivo"
    assert eliminar_suscripcion_push(endpoint) is True


def test_notificacion_push_contiene_acceso_al_chat(tmp_path, monkeypatch):
    endpoint = "https://push.example.test/envio-prueba"
    clave = tmp_path / "vapid.pem"
    clave.write_text("privada-de-prueba")
    recibidos = []

    eliminar_suscripcion_push(endpoint)
    guardar_suscripcion_push("tester", _suscripcion(endpoint))
    monkeypatch.setattr(push_notifications.settings, "PUSH_VAPID_PRIVATE_KEY_PATH", str(clave))
    monkeypatch.setattr(push_notifications.settings, "PUSH_VAPID_PUBLIC_KEY", "publica-de-prueba")
    monkeypatch.setattr(
        push_notifications,
        "webpush",
        lambda **argumentos: recibidos.append(argumentos),
    )

    resultado = asyncio.run(
        push_notifications.notificar_panel_push(
            "50760000000", "Cliente Prueba", "Necesito atención"
        )
    )

    assert resultado["configurado"] is True
    assert resultado["enviadas"] >= 1
    assert any("/admin?telefono=50760000000" in envio["data"] for envio in recibidos)
    eliminar_suscripcion_push(endpoint)
