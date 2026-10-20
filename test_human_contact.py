from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.services import human_contact as contact
from app.services.attention_context import attention_context
from app.ai import orchestrator as bot

@pytest.fixture(autouse=True)
def no_voice(monkeypatch):
    monkeypatch.setattr(contact.settings,'CUBICO_HUMAN_CALL_PHONE','')
    monkeypatch.setattr(contact.settings,'CUBICO_HUMAN_CALL_VERIFIED',False)

@pytest.mark.parametrize('text',['Necesito un teléfono para llamar y que me conteste un humano','Puedo llamarlos','Me pueden hacer una llamada','Llámame por favor'])
def test_voice_intents(text):
    assert contact.call_request(text)


def test_invalid_number_requires_voice_context():
    text='Ese numero dice que no es correcto'
    assert contact.call_request(text,[{'content':'Puedes llamar al número del local'}])
    assert not contact.call_request(text,[{'content':'Pásame el tracking'}])
    assert not contact.call_request('el tracking no funciona')


def test_general_number_is_not_voice_proof(monkeypatch):
    monkeypatch.setattr(contact.settings,'CUBICO_LOCAL_PHONE','6000-1111')
    monkeypatch.setattr(contact.settings,'CUBICO_HUMAN_CALL_PHONE','6000-2222')
    assert contact.verified_call_phone() is None
    assert '6000-1111' not in contact.contact_rules()
    assert '6000-2222' not in contact.call_reply()
    monkeypatch.setattr(contact.settings,'CUBICO_HUMAN_CALL_VERIFIED',True)
    assert contact.verified_call_phone()=='6000-2222'
    assert '6000-2222' in contact.call_reply()
    monkeypatch.setattr(contact.settings,'CUBICO_HUMAN_CALL_PHONE','mal-configurado')
    assert contact.verified_call_phone() is None


def test_call_guard_keeps_previous_issue_and_never_calls_model(monkeypatch):
    monkeypatch.setattr(bot,'obtener_sesion_existente',lambda _:SimpleNamespace(motivo_escalamiento='Entrega pendiente y tarifa en revisión'))
    update=Mock();model=Mock(side_effect=AssertionError('No model required'))
    monkeypatch.setattr(bot,'actualizar_sesion',update)
    monkeypatch.setattr(bot,'call_anthropic',model)
    answer=bot.generar_respuesta('Necesito un teléfono para llamar','507test')
    assert 'No tengo un número confirmado' in answer
    assert 'te llamarán' not in answer
    reason=update.call_args.kwargs['motivo_escalamiento']
    assert 'Entrega pendiente' in reason and update.call_args.kwargs['necesita_atencion_humana']
    assert attention_context(reason,[])['categoria']=='Solicitud de contacto humano'
    model.assert_not_called()


def test_editor_inherits_current_voice_policy(monkeypatch):
    monkeypatch.setattr(bot,'obtener_sesion_existente',lambda _:None)
    model=Mock(return_value=SimpleNamespace(content=[SimpleNamespace(type='text',text='Lo revisamos por este chat.')]))
    monkeypatch.setattr(bot,'call_anthropic',model)
    bot.redactar_respuesta_de_asesor('Quiero llamar','Responde por aquí','507test')
    assert 'No hay un número confirmado' in str(model.call_args.kwargs['system'])
