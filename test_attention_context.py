import unittest
from app.services.attention_context import attention_context

class AttentionContextTests(unittest.TestCase):
    def test_inactive_does_not_reopen_old_reason(self):
        self.assertIsNone(attention_context('Tracking fallido', [], False))

    def test_real_messages_and_no_invented_amount(self):
        history = [{'role': 'user', 'content': 'El total porfa', 'timestamp': 'a'},
                   {'role': 'humano', 'content': 'Voy a revisar', 'timestamp': 'b'},
                   {'role': 'system', 'content': 'private system'}]
        ctx = attention_context('Saldo por verificar', history)
        self.assertEqual(ctx['ultimo_cliente']['texto'], 'El total porfa')
        self.assertEqual(ctx['ultima_respuesta']['texto'], 'Voy a revisar')
        self.assertNotIn('$', ctx['borrador'])
        self.assertIn('facturas', ctx['pasos'][0])
        self.assertNotIn('private system', str(ctx))

    def test_distinct_actions(self):
        for reason, category in [('Paquete MALID', 'Paquete mal identificado'),
                                 ('Tracking falló dos veces', 'Consulta de tracking pendiente'),
                                 ('Ubicación de retiro sin pin vigente', 'Ubicación por confirmar'),
                                 ('Demora de 6 días en Miami', 'Demora en Miami'),
                                 ('Límite de intentos de identidad', 'Verificación pendiente')]:
            with self.subTest(reason=reason):
                ctx = attention_context(reason, [])
                self.assertEqual(ctx['categoria'], category)
                self.assertTrue(ctx['pasos'])
                self.assertIsNone(ctx['ultimo_cliente'])

    def test_old_reason_is_not_claimed_as_trigger(self):
        ctx = attention_context('', [{'role': 'user', 'content': '<img src=x>'}])
        self.assertIn('No se registró', ctx['motivo'])
        self.assertIn('no necesariamente', ctx['nota'])
        self.assertEqual(ctx['ultimo_cliente']['texto'], '<img src=x>')

if __name__ == '__main__':
    unittest.main()
