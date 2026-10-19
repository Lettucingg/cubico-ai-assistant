from unittest.mock import Mock
from sqlalchemy.exc import SQLAlchemyError
from app.api import panel
from app.db import session_store as store

def test_customer_database_failure_does_not_hide_chat_list(monkeypatch):
    sessions=[store.obtener_o_crear_sesion('loading-1'),store.obtener_o_crear_sesion('loading-2')]
    for s in sessions:s.codigo_cliente_verificado='CBC-test'
    monkeypatch.setattr(panel,'listar_todas_sesiones',lambda:sessions)
    lookup=Mock(side_effect=SQLAlchemyError('customer database unavailable'))
    monkeypatch.setattr(panel,'obtener_nombre_completo_cliente',lookup)
    monkeypatch.setattr(panel,'obtener_uso_por_telefono',lambda _: {})
    result=panel.listar_conversaciones('alexander')
    assert [c['telefono'] for c in result]==['loading-1','loading-2']
    assert all(c['nombre'] is None for c in result)
    lookup.assert_called_once() # No repeated attempts against an unavailable database.
