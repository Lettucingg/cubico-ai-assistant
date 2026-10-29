"""Delivery metadata regressions; runs without provider credentials or API calls."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from app.services.conversation_context import clean_delivery_labels, delivery_context, context_window


def load_function(name, tree=None, **namespace):
    tree=tree or ast.parse(Path('app/ai/orchestrator.py').read_text())
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
    env={'clean_delivery_labels':clean_delivery_labels,'delivery_context':delivery_context,'context_window':context_window,**namespace}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<production function>','exec'),env)
    return env[name]


class DeliveryLabelsTests(unittest.TestCase):
    def test_reported_reply(self):
        self.assertEqual(clean_delivery_labels('[Estado de envío: delivered] Dale, cualquier cosa me dices.'),'Dale, cualquier cosa me dices.')

    def test_all_states_and_repeated_prefixes(self):
        for status in ['accepted','sent','delivered','read','failed','pending','desconocido']:
            self.assertEqual(clean_delivery_labels(f'[Estado de envío: {status}] [Estado de envío: read] Hola'),'Hola')
            note=delivery_context(status)
            self.assertEqual(clean_delivery_labels(note+' Hola'),'Hola')

    def test_legitimate_customer_text_is_preserved(self):
        for text in ['Tu paquete está disponible. Total: $10.00.','Mi pedido aparece delivered.','¿Qué significa [Estado de envío: delivered]?','[Estado de cuenta: pendiente] Debes $10.00.']:
            self.assertEqual(clean_delivery_labels(text),text)

    def test_empty_and_metadata_only(self):
        self.assertEqual(clean_delivery_labels(None),'')
        self.assertEqual(clean_delivery_labels('[Estado de envío: sent]'),'')

    def test_failed_delivery_retained_successful_not_imitated(self):
        normalize=load_function('normalizar_historial_para_claude',_contenido_historial_para_ia=lambda item:item['content'])
        incoming={'role':'user','content':'[Estado de envío: read] ¿Qué significa?'}
        history=[incoming,{'role':'assistant','content':'[Estado de envío: delivered] Dale.','estado_entrega':'delivered'},
                 {'role':'humano','autor_tipo':'humano','content':'Ya avisé al equipo.','estado_entrega':'failed'}]
        out=normalize(history)
        self.assertEqual(out[0]['content'],incoming['content'])
        self.assertEqual(out[1],{'role':'assistant','content':'Dale.'})
        self.assertIn('estado=failed',out[2]['content'])
        self.assertIn('no por Bruno',out[2]['content'])
        self.assertEqual(history[1]['content'],'[Estado de envío: delivered] Dale.')

    def test_automatic_response_boundary(self):
        extract=load_function('_extraer_texto')
        response=SimpleNamespace(content=[SimpleNamespace(type='text',text='[Estado de envío: delivered] Dale, cualquier cosa me dices.')])
        self.assertEqual(extract(response),'Dale, cualquier cosa me dices.')
        response.content[0].text='[Estado de envío: read]'
        self.assertIsNone(extract(response))

    def test_assisted_draft_boundary(self):
        draft=load_function('redactar_respuesta_de_asesor',obtener_sesion_existente=lambda _:None,
            memory_digest=lambda *a:'',_contenido_historial_para_ia=lambda item:item['content'],
            json=__import__('json'),cliente_claude=None,CONTEXT_RULES='',DELIVERY_RULES='',
            contact_rules=lambda:'',payment_rules=lambda:'',campaign_rules=lambda:'',location_rules=lambda:'',active_context=lambda *a:[],system_with_context=lambda *a:'',
            call_anthropic=lambda *a,**k:SimpleNamespace(content=[SimpleNamespace(type='text',text='[Estado de envío: delivered] Ya reviso tu pedido.')]))
        self.assertEqual(draft('Pedido','Ya reviso tu pedido.','507test'),'Ya reviso tu pedido.')


if __name__=='__main__':unittest.main()
