import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import httpx
import pytest
from app.services import payment_policy as policy
from app.tools import comprobantes as receipts
from app.ai import orchestrator as bot
from app.api import whatsapp


@pytest.fixture(autouse=True)
def unconfigured_bank(monkeypatch):
    monkeypatch.setattr(policy.settings,'CUBICO_BANK_TRANSFER_ENABLED',False)
    monkeypatch.setattr(policy.settings,'CUBICO_PAYMENT_ACCOUNT','OLD-ACCOUNT-DO-NOT-PUBLISH')
    monkeypatch.setattr(policy.settings,'CUBICO_PAYMENT_ACCOUNT_HOLDER','OLD-HOLDER-DO-NOT-PUBLISH')
    monkeypatch.setattr(policy.settings,'CUBICO_YAPPY_ENABLED',False)


def test_old_bank_number_not_offered_without_explicit_activation(monkeypatch):
    assert policy.bank_transfer_details() is None
    assert 'OLD-ACCOUNT' not in policy.payment_rules()
    assert 'OLD-HOLDER' not in str(policy.payment_options())
    assert 'cuenta bancaria propia habilitada' in policy.payment_rules()
    monkeypatch.setattr(policy.settings,'CUBICO_BANK_TRANSFER_ENABLED',True)
    monkeypatch.setattr(policy.settings,'CUBICO_PAYMENT_ACCOUNT_HOLDER','')
    assert policy.bank_transfer_details() is None
    monkeypatch.setattr(policy.settings,'CUBICO_PAYMENT_ACCOUNT_HOLDER','Titular confirmado')
    assert 'Titular confirmado' in policy.bank_transfer_details()
    assert 'No lo presentes como cuenta propia' in policy.payment_rules()


@pytest.mark.parametrize('reply',[
    'La transferencia fue a SHIP2NEXO y no a Cúbico. Paga a nuestra cuenta Banco General 123.',
    'No puedo marcarte como pagado porque el destinatario es otra empresa.',
    'No has pagado; vuelve a enviar el dinero.',
    'Perfecto, no debes nada. Ya registré el pago.',
])
def test_receipt_prose_cannot_reject_destination_request_repayment_or_confirm_paid(reply):
    result=receipts.interpretar_analisis_imagen('ES_COMPROBANTE: sí\nMONTO: 85.80\nREFERENCIA: TEST-REF\nMETODO: transferencia\n===RESPUESTA===\n'+reply)
    assert result['es_comprobante']
    assert result['texto_respuesta']==policy.receipt_acknowledgement()
    assert '85.80' in result['detalle_completo'] and 'TEST-REF' in result['detalle_completo']
    assert 'SHIP2NEXO' not in result['texto_respuesta'] and 'Banco General' not in result['texto_respuesta']


def test_vision_gets_current_policy_and_classifies_even_other_beneficiary(monkeypatch):
    call=Mock(return_value=SimpleNamespace(content=[SimpleNamespace(type='text',text='ES_COMPROBANTE: si\nMONTO: 85.80\n===RESPUESTA===\nNuestra cuenta es otra.')]))
    monkeypatch.setattr(receipts,'call_anthropic',call)
    result=receipts.analizar_imagen_cliente(b'\xff\xd8test','Listo, no debo nada','test-phone')
    system=call.call_args.kwargs['system'][0]['text']
    assert 'cuenta bancaria propia habilitada' in system
    assert 'OLD-ACCOUNT' not in system
    assert 'otra marca' in call.call_args.kwargs['messages'][0]['content'][1]['text']
    assert result['texto_respuesta']==policy.receipt_acknowledgement()


@pytest.mark.parametrize('message',['Siempre hago el pago ahi','Siempre pago ahí','Siempre he pagado a esa cuenta'])
def test_habitual_payment_followup_does_not_argue_or_send_new_account(message,monkeypatch):
    monkeypatch.setattr(bot,'obtener_sesion_existente',lambda _:SimpleNamespace(pago_reportado=True,pago_confirmado=False))
    model=Mock(side_effect=AssertionError('No AI required'));monkeypatch.setattr(bot,'call_anthropic',model)
    answer=bot.generar_respuesta(message,'test')
    assert answer==policy.receipt_followup_reply()
    assert 'No repitas el pago' in answer and 'OLD-ACCOUNT' not in answer
    model.assert_not_called()


def test_whatsapp_boundary_queues_receipt_but_only_sends_safe_ack(monkeypatch):
    session=SimpleNamespace(telefono='test-phone',atencion_humana_directa=False,necesita_atencion_humana=False,
                            motivo_escalamiento=None,entregado=False)
    monkeypatch.setattr(whatsapp,'obtener_o_crear_sesion',lambda _:session)
    monkeypatch.setattr(whatsapp,'descargar_imagen_de_whatsapp',AsyncMock(return_value=b'\xff\xd8test'))
    monkeypatch.setattr(whatsapp,'analizar_imagen_cliente',lambda *args:{'es_comprobante':True,'contexto_visual':None,
        'texto_respuesta':'Paga otra vez a Banco General OLD-ACCOUNT-DO-NOT-PUBLISH',
        'detalle_completo':'ES_COMPROBANTE: si\nMONTO: 85.80\nREFERENCIA: TEST-REF\nMETODO: transferencia'})
    changes=Mock();history=Mock();notify=AsyncMock();send=AsyncMock(return_value=httpx.Response(200,json={'messages':[{'id':'wamid-test'}]}))
    monkeypatch.setattr(whatsapp,'actualizar_sesion',changes)
    monkeypatch.setattr(whatsapp,'agregar_al_historial',history)
    monkeypatch.setattr(whatsapp,'notificar_equipo_comprobante',notify)
    monkeypatch.setattr(whatsapp,'enviar_respuesta_natural',send)
    asyncio.run(whatsapp._procesar_mensaje_en_segundo_plano_sin_candado({'telefono':'test-phone','tipo':'image',
                'media_id':'test-media','texto':'Listo, no debo nada','message_id':'wamid-in'}))
    assert send.call_args.args[1]==policy.receipt_acknowledgement()
    assert changes.call_args.kwargs['pago_reportado'] is True
    assert changes.call_args.kwargs['pago_confirmado'] is False
    assert changes.call_args.kwargs['monto_pago_reportado']==85.80
    notify.assert_awaited_once()
    assert 'OLD-ACCOUNT' not in str(history.call_args_list)


@pytest.mark.parametrize('question',['¿Cuál es la cuenta?','Número de cuenta','Me pasas la cuenta para pagar','¿Tienen cuenta bancaria?'])
def test_direct_bank_questions_never_share_old_number(question):
    result=bot.buscar_respuesta_fija(question)
    assert result is not None and 'No tengo datos bancarios habilitados' in result
    assert 'OLD-ACCOUNT' not in result
