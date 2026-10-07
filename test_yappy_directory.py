"""Regresión: compartir un número no implica inscripción en el directorio."""
import pytest
from app.ai import orchestrator


@pytest.mark.parametrize('question', [
    '¿Están en el directorio de Yappy?',
    'Estan en el directorio de Yappy',
    '¿Ustedes aparecen en el directorio Yappy?',
    '¿Ya están en el directorio de Yappy?',
    '¿Con qué nombre aparecen en el directorio de Yappy?',
    '¿Cómo los busco en el directorio de Yappy?',
])
def test_directory_answer_does_not_require_identity_or_model(question, monkeypatch):
    monkeypatch.setattr(orchestrator, 'CUBICO_PAYMENT_YAPPY', '6000-0000')
    def unexpected_model(**kwargs):
        raise AssertionError('A confirmed public fact should not require AI')
    monkeypatch.setattr(orchestrator.cliente_claude.messages, 'create', unexpected_model)
    answer = orchestrator.generar_respuesta(question, '5070000')
    assert answer == 'Todavía no estamos en el directorio de Yappy. Por ahora el pago por Yappy se hace al número 6000-0000.'


def test_previous_wrong_answer_does_not_override_confirmed_fact(monkeypatch):
    monkeypatch.setattr(orchestrator, 'obtener_nombre_completo_cliente', lambda code: {'encontrado': True, 'nombre_completo': 'Cliente Prueba'})
    monkeypatch.setattr(orchestrator.cliente_claude.messages, 'create', lambda **kw: pytest.fail('No model call expected'))
    answer = orchestrator.generar_respuesta('¿Están en el directorio de Yappy?', '5070000', 'CBC-0018', [
        {'role': 'assistant', 'content': 'Sí, puedes buscarnos en Yappy como Cúbico.'},
    ])
    assert answer.startswith('Todavía no estamos en el directorio de Yappy.')


@pytest.mark.parametrize('text', [
    'Tampoco aparecen en el directorio de Yappy con ese nombre, no hay forma de confirmar que son ustedes',
    'Ese número en Yappy es un número personal',
    'No aparecen en el directorio, quiero hablar con una persona',
    '¿Están en el directorio de Yappy? También necesito confirmar cuánto debo.',
    'Mi pago de Yappy no aparece en la factura',
    'Escríbanme por el teléfono viejo de Ship2Nexo, no tengo un contrato con Cúbico',
])
def test_complaints_and_multiple_requests_keep_contextual_tool_flow(text):
    assert orchestrator.buscar_respuesta_fija(text) is None
