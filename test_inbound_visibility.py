"""El aviso nunca debe adelantarse al historial persistido."""
import asyncio
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.api import whatsapp as wa
from app.db import session_store as store


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'inbox.db'}")
    store.BaseSesiones.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(store, 'SessionSesiones', factory)
    store.obtener_o_crear_sesion('50760000000')
    return factory


def test_push_y_buffer_solo_despues_de_guardar(database, monkeypatch):
    message = {'telefono': '50760000000', 'texto': 'Hola', 'tipo': 'text', 'message_id': 'IN-1'}
    monkeypatch.setattr(wa, 'obtener_o_crear_sesion', store.obtener_o_crear_sesion)
    calls = []
    async def push(*args):
        assert store.obtener_sesion_existente(message['telefono']).obtener_historial()[0]['content'] == 'Hola'
        calls.append('push')
    async def buffer(msg):
        assert msg['_inbound_ids'] == ['IN-1']
        assert len(store.obtener_sesion_existente(message['telefono']).obtener_historial()) == 1
        calls.append('buffer')
    monkeypatch.setattr(wa, 'notificar_panel_push', push)
    monkeypatch.setattr(wa, 'agregar_mensaje_a_buffer', buffer)
    asyncio.run(wa.procesar_entrada_con_push(message))
    assert set(calls) == {'push', 'buffer'}


def test_imagen_no_desaparece_si_falla_procesamiento(database, monkeypatch):
    msg = {'telefono': '50760000000', 'texto': None, 'tipo': 'image', 'media_id': 'IMG-1', 'message_id': 'IN-2'}
    async def fail(msg):
        raise RuntimeError('vision unavailable')
    async def push(*args):
        return None
    monkeypatch.setattr(wa, 'agregar_mensaje_a_buffer', fail)
    monkeypatch.setattr(wa, 'notificar_panel_push', push)
    with pytest.raises(RuntimeError):
        asyncio.run(wa.procesar_entrada_con_push(msg))
    h = store.obtener_sesion_existente(msg['telefono']).obtener_historial()
    assert len(h) == 1 and h[0]['media_id'] == 'IMG-1'


def test_rafaga_guardada_no_se_duplica_ni_pierde_textos(database):
    for mid, text in [('A', 'Hola'), ('B', 'Tengo una consulta')]:
        store.agregar_al_historial('50760000000', 'user', text, whatsapp_message_id=mid, tipo='text')
    store.agregar_al_historial('50760000000', 'user', 'Hola\nTengo una consulta', whatsapp_message_id='B')
    h = store.obtener_sesion_existente('50760000000').obtener_historial()
    assert [m['content'] for m in h] == ['Hola', 'Tengo una consulta']
    a = {'tipo': 'text', 'texto': 'Hola', 'message_id': 'A', '_inbound_ids': ['A']}
    b = {'tipo': 'text', 'texto': 'Tengo una consulta', 'message_id': 'B', '_inbound_ids': ['B']}
    combined, _ = wa.combinar_mensajes_para_buffer(a, b)
    assert combined['_inbound_ids'] == ['A', 'B']
    assert wa._historial_previo_a_entrada(SimpleNamespace(obtener_historial=lambda: h), combined) == []


def test_contexto_visual_enriquece_imagen_original(database):
    store.agregar_al_historial('50760000000', 'user', '[Cliente envió una imagen]', tipo='image', media_id='IMG', whatsapp_message_id='IMAGE')
    store.agregar_al_historial('50760000000', 'user', '¿Qué es?', tipo='text', whatsapp_message_id='TEXT')
    store.agregar_al_historial('50760000000', 'user', '¿Qué es?', tipo='image', media_id='IMG', whatsapp_message_id='TEXT', contexto_ia='Factura visible')
    h = store.obtener_sesion_existente('50760000000').obtener_historial()
    assert len(h) == 2
    assert h[0]['contexto_ia'] == 'Factura visible'
    assert h[0]['whatsapp_message_id'] == 'IMAGE'
    assert h[1]['content'] == '¿Qué es?'
