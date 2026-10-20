from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.services import staff_tracking as tracking, internal_assistant as service
from app.ai import orchestrator as bot
from app.services.attention_context import attention_context


def session(code=None):
    return SimpleNamespace(telefono='507test',codigo_cliente_verificado=code,tipo_cliente_verificado=None,obtener_historial=lambda:[])


def test_pasted_tracking_is_read_only_and_does_not_query_customer_accounts(monkeypatch):
    lookup=Mock(return_value={'encontrado':True,'estado':'Recibido en Miami','ubicacion':'Miami','fuente':'ptyfreight','cliente':'NO EXPONER','saldo':50})
    monkeypatch.setattr(tracking,'consultar_tracking',lookup)
    for name in ['consultar_facturas_por_codigo','consultar_paquetes_por_codigo','consultar_ultimo_pago_por_codigo']:
        monkeypatch.setattr(service,name,Mock(side_effect=AssertionError('No account lookup')))
    result=service.query_chat(session(),'El cliente pregunta por 9261290416110741315371 ¿qué le contesto?','borrador')
    lookup.assert_called_once_with('9261290416110741315371')
    assert result['alcance']=='tracking_publico' and result['privado']
    assert 'Miami' in result['borrador'] and 'No confirma' in result['borrador']
    assert 'NO EXPONER' not in str(result) and 'ptyfreight' not in str(result)
    assert result['codigo_cliente'] is None


def test_no_record_failure_and_malid_are_distinct(monkeypatch):
    lookup=Mock(return_value={'encontrado':False})
    monkeypatch.setattr(tracking,'consultar_tracking',lookup)
    result=service.query_chat(session(),'92612903364896541537968877','borrador')
    assert 'No aparece registrado' in result['borrador'] and 'posible' in result['borrador']
    lookup.return_value={'encontrado':False,'error':True}
    result=service.query_chat(session(),'92612903364896541537968877','borrador')
    assert 'No pude consultar' in result['borrador']
    assert not result['datos']['trackings'][0]['disponible']
    lookup.return_value={'encontrado':True,'identificacion_incorrecta':True,'estado':'Disponible','fuente':'ptyfreight'}
    result=service.query_chat(session(),'92612903364896541537968877','borrador')
    assert 'mal identificado' in result['borrador']
    assert 'confirmar la ubicación' in result['borrador']
    assert 'listo para retirar' not in result['borrador']


def test_no_tracking_does_not_unlock_private_account_data():
    with pytest.raises(service.UnlinkedCustomer):service.query_chat(session(),'Cuánto debe')
    assert tracking.extract_trackings('CBC000012 FAC000012 OP000012 https://host/92612903364896541537968877 a1234567@example.com ../92612903364896541537968877')==[]
    assert tracking.extract_trackings('ABC1234567 ABC1234567')==['ABC1234567']
    assert tracking.extract_trackings('9'*41)==[]


def test_three_tracking_limit_and_failure_has_no_private_error(monkeypatch):
    lookup=Mock(side_effect=RuntimeError('secret password at provider'))
    monkeypatch.setattr(tracking,'consultar_tracking',lookup)
    result=service.query_chat(session(),'1234567890 1234567891 1234567892 1234567893')
    lookup.assert_not_called();assert 'tres' in result['respuesta']
    result=service.query_chat(session(),'1234567890','consulta')
    assert 'secret' not in str(result) and result['borrador']==''


def test_unreceived_delivery_marks_clear_attention_without_guessing_state(monkeypatch):
    update=Mock();model=Mock(side_effect=AssertionError('No model guessing'))
    monkeypatch.setattr(bot,'actualizar_sesion',update)
    monkeypatch.setattr(bot,'obtener_sesion_existente',lambda _:SimpleNamespace(motivo_escalamiento='Tarifa pendiente'))
    monkeypatch.setattr(bot,'call_anthropic',model)
    result=bot.generar_respuesta('No he recibido el paquete','507test')
    assert 'está en ruta' not in result and 'retirarlo hoy' not in result
    reason=update.call_args.kwargs['motivo_escalamiento']
    assert 'Tarifa pendiente' in reason
    assert attention_context(reason,[])['categoria']=='Entrega pendiente por revisar'
    model.assert_not_called()


def test_authenticated_public_query_works_without_linking_or_sending(monkeypatch):
    import asyncio
    from app.api import panel
    current=session()
    monkeypatch.setattr(panel,'obtener_sesion_existente',lambda _:current)
    monkeypatch.setattr(tracking,'consultar_tracking',lambda _: {'encontrado':False})
    sent=Mock(side_effect=AssertionError('Must not send'))
    monkeypatch.setattr(panel,'enviar_respuesta_natural',sent)
    result=asyncio.run(panel.consultar_bruno_panel('507test',panel.ConsultaBrunoPayload(pregunta='9261290416110741315371',modo='borrador'),'alexander'))
    assert result['alcance']=='tracking_publico' and result['borrador']
    sent.assert_not_called()


def test_reply_request_can_use_tracking_in_last_customer_message(monkeypatch):
    current=session()
    current.obtener_historial=lambda:[{'role':'user','content':'Dónde está 9261290416110741315371'},
                                     {'role':'humano','content':'Operador CBC-0001'}]
    monkeypatch.setattr(tracking,'consultar_tracking',lambda _: {'encontrado':True,'estado':'En tránsito','ubicacion':'Miami'})
    result=service.query_chat(current,'Qué le contesto al último mensaje','borrador')
    assert '9261290416110741315371' in result['borrador']
    assert 'en tránsito' in result['borrador'] and 'recibido en Miami' not in result['borrador']
