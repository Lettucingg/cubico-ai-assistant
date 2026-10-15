"""Run without provider credentials; no network or real notifications."""
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch, Mock


class PushSelfTest(unittest.TestCase):
    def load_push(self):
        config = ModuleType('app.core.config')
        config.settings = SimpleNamespace()
        prefs = ModuleType('app.services.notification_preferences')
        prefs.permite = lambda *_: True
        prefs.obtener = lambda _: 'ambos'
        store = ModuleType('app.db.session_store')
        store.eliminar_suscripcion_push = Mock()
        store.listar_suscripciones_push = lambda: []
        spec = importlib.util.spec_from_file_location('isolated_push', Path('app/services/push_notifications.py'))
        module = importlib.util.module_from_spec(spec)
        return module, spec, {'app.core.config': config, 'app.services.notification_preferences': prefs, 'app.db.session_store': store}, prefs

    def test_test_targets_only_authenticated_user_and_respects_category(self):
        m, spec, modules, prefs = self.load_push()
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(m)
            m._enviar_a_dispositivos = Mock(return_value={'enviadas':1,'configurado':True})
            for preference in ['chats', 'alertas', 'ambos']:
                prefs.obtener = lambda _, p=preference: p
                result = asyncio.run(m.enviar_prueba_push('teresa'))
                payload, users = m._enviar_a_dispositivos.call_args.args
                self.assertEqual(users, {'teresa'})
                self.assertEqual(payload['categoria'], 'chats' if preference == 'chats' else 'alertas')
                self.assertNotIn('telefono', payload)
                self.assertEqual(result['enviadas'],1)

    def test_zero_deliveries_not_relabelled_success(self):
        m, spec, modules, _ = self.load_push()
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(m)
            m._enviar_a_dispositivos = Mock(return_value={'enviadas':0,'configurado':False})
            self.assertEqual(asyncio.run(m.enviar_prueba_push('teresa')), {'enviadas':0,'configurado':False})

if __name__ == '__main__':
    unittest.main()
