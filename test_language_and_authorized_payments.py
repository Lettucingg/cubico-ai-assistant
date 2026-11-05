from types import SimpleNamespace as NS
from unittest.mock import Mock
import pytest
from app.services.conversation_language import reply_language
from app.services import payment_policy as policy
from app.ai import orchestrator as bot


@pytest.mark.parametrize('message', ['ok', '123456789000', '👍', ''])
def test_language_survives_neutral_messages_and_spanish_internal_prose(message):
    history=[{'role':'user','content':'Please tell me when my package arrives'},
             {'role':'assistant','content':'El equipo revisará el estado'},
             {'role':'humano','content':'Aquí te ayudamos en español'}]
    assert reply_language(message,history)=='en'


def test_language_uses_customer_words_and_explicit_preference():
    assert reply_language('¿Dónde está mi paquete?')=='es'
    assert reply_language('Please answer in English')=='en'
    assert reply_language('12345678',[{'role':'user','content':'Please reply in English'}])=='en'
    assert reply_language('Responde en español',[{'role':'user','content':'Please reply in English'}])=='es'
    assert reply_language('[DATOS LEÍDOS DE LA IMAGEN: comprobante de pago]',
                          [{'role':'user','content':'I paid for my package'}])=='en'


def authorized(monkeypatch):
    for key,value in {'CUBICO_LEGACY_PAYMENTS_ENABLED':True,'CUBICO_BANK_TRANSFER_ENABLED':False,
                      'CUBICO_YAPPY_ENABLED':False,'CUBICO_PAYMENT_ACCOUNT':'TEST-ACCOUNT',
                      'CUBICO_PAYMENT_ACCOUNT_HOLDER':'TEST-HOLDER','CUBICO_PAYMENT_YAPPY':'TEST-YAPPY'}.items():
        monkeypatch.setattr(policy.settings,key,value)


def test_authorized_previous_destinations_work_without_claiming_own_account(monkeypatch):
    authorized(monkeypatch)
    assert 'TEST-ACCOUNT' in policy.bank_transfer_reply()
    assert 'TEST-YAPPY' in policy.yappy_reply()
    assert 'TEST-HOLDER' not in str(policy.payment_options())
    assert 'TEST-HOLDER' not in policy.bank_transfer_reply()
    assert 'directorio comercial' in policy.yappy_reply(directory=True)
    assert 'Puedes pagar' in policy.yappy_reply(directory=True)
    assert 'no tiene cuenta propia' in policy.payment_rules()
    monkeypatch.setattr(policy.settings,'CUBICO_PAYMENT_ACCOUNT','')
    monkeypatch.setattr(policy.settings,'CUBICO_PAYMENT_YAPPY','')
    assert 'TEST-' not in str(policy.payment_options())


def test_english_fixed_payment_and_receipt_replies_do_not_call_model(monkeypatch):
    authorized(monkeypatch)
    call=Mock(side_effect=AssertionError('No metered call allowed'))
    monkeypatch.setattr(bot,'call_anthropic',call)
    monkeypatch.setattr(bot,'obtener_sesion_existente',lambda _:NS(pago_reportado=True,pago_confirmado=False))
    history=[{'role':'user','content':'Hello, I need to pay for my package'}]
    assert 'You can pay' in bot.generar_respuesta('Yappy','test',historial=history)
    assert 'TEST-ACCOUNT' in bot.generar_respuesta('bank account','test',historial=history)
    assert 'Please do not repeat' in bot.generar_respuesta('I always pay there','test',historial=history)
    assert policy.receipt_acknowledgement('en').startswith('Thank you')
    call.assert_not_called()


def test_actual_model_prompt_keeps_english_with_spanish_operational_notice(monkeypatch):
    monkeypatch.setattr(bot,'active_context',lambda *a:[])
    monkeypatch.setattr(bot,'system_with_context',lambda text,notices:text+'\nAVISO INTERNO: el reparto está suspendido')
    monkeypatch.setattr(bot,'location_rules',lambda:'')
    call=Mock(return_value=NS(stop_reason='end_turn',content=[NS(type='text',text='Our team will confirm the delivery details.')]))
    monkeypatch.setattr(bot,'call_anthropic',call)
    answer=bot.generar_respuesta('Could you explain whether customs duties are included?','test')
    assert answer.startswith('Our team')
    assert 'IDIOMA DE RESPUESTA: English' in str(call.call_args.kwargs['system'])
    assert 'el reparto está suspendido' in call.call_args.kwargs['system']
    call.assert_called_once()


def test_assisted_editor_uses_customer_language_not_spanish_operator_draft(monkeypatch):
    monkeypatch.setattr(bot,'obtener_sesion_existente',lambda _:NS(obtener_historial=lambda:[{'role':'user','content':'Where can I pay?'}]))
    monkeypatch.setattr(bot,'active_context',lambda *a:[])
    call=Mock(return_value=NS(content=[NS(type='text',text='Please send your receipt for review.')]))
    monkeypatch.setattr(bot,'call_anthropic',call)
    bot.redactar_respuesta_de_asesor('Where can I pay?','Pídele el comprobante','test')
    assert 'IDIOMA DE RESPUESTA: English' in str(call.call_args.kwargs['system'])
