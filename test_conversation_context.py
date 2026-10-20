from types import SimpleNamespace
from unittest.mock import Mock
from app.services.conversation_context import context_window, memory_digest
from app.ai import orchestrator as bot


def test_adaptive_budget_and_no_mutation():
    history=[{'role':'user','content':f'consulta número {n}'} for n in range(100)]
    assert len(context_window(history,'precio transporte internacional China'))==8
    assert len(context_window(history,'dónde está mi paquete'))==16
    assert len(context_window(history,'sí'))==16
    assert len(history)==100


def test_digest_uses_relevant_customer_and_team_quotes_not_model_guesses():
    history=[{'role':'assistant','content':'El retiro quedó resuelto y pagado'},
             {'role':'user','content':'Necesito retiro del paquete pendiente'},
             {'role':'humano','content':'Te enviamos ubicación para retiro','estado_entrega':'failed'}]
    history += [{'role':'assistant','content':'Información reciente'}]*16
    digest=memory_digest(history,'retiro')
    assert 'resuelto y pagado' not in digest
    assert 'Necesito retiro' in digest and 'failed' in digest
    assert 'no acredita gestiones' in digest
    history[2]['estado_entrega']='delivered'
    assert 'failed' not in memory_digest(history,'retiro')


def test_bounded_digest_and_messages():
    history=[{'role':'user','content':'paquete ubicación '+('x'*20000)} for _ in range(1000)]
    digest=memory_digest(history,'paquete')
    assert digest.count('"cita"')==4 and len(digest)<1800
    normalized=bot.normalizar_historial_para_claude(history,'paquete')
    assert len(normalized)==16
    assert all(len(m['content'])<=1600 for m in normalized)
    assert memory_digest([], 'retiro')==''


def test_failed_operator_not_customer_and_status_not_lost():
    messages=bot.normalizar_historial_para_claude([
        {'role':'humano','autor_tipo':'humano','operador':'alexander','content':'Ya avisé al equipo','estado_entrega':'failed'}])
    assert messages[0]['role']=='assistant'
    assert 'failed' in messages[0]['content'] and 'no por Bruno' in messages[0]['content']


def test_draft_uses_digest_without_extra_model_call(monkeypatch):
    history=[{'role':'user','content':'Quiero retiro del paquete antiguo'}]
    history += [{'role':'assistant','content':'Respuesta reciente'}]*16
    monkeypatch.setattr(bot,'obtener_sesion_existente',lambda _:SimpleNamespace(obtener_historial=lambda:history))
    model=Mock(return_value=SimpleNamespace(content=[SimpleNamespace(type='text',text='Coordinamos el retiro.')]))
    monkeypatch.setattr(bot,'call_anthropic',model)
    bot.redactar_respuesta_de_asesor('retiro','Coordinar retiro','507test')
    model.assert_called_once()
    assert 'paquete antiguo' in model.call_args.kwargs['messages'][0]['content']
    assert 'saldos, pagos y paquetes actuales' in str(model.call_args.kwargs['system'])


def test_thanks_short_and_greeting_does_not_bypass_context(monkeypatch):
    history=[{'role':'user','content':'Cuánto debo de mis paquetes'}]
    model=Mock(return_value=SimpleNamespace(content=[SimpleNamespace(type='text',text='Seguimos con tu consulta del saldo.')],stop_reason='end_turn'))
    monkeypatch.setattr(bot,'call_anthropic',model)
    monkeypatch.setattr(bot,'active_context',lambda *a:[])
    assert bot.generar_respuesta('gracias','507test',historial=history)=='Con gusto.'
    model.assert_not_called()
    result=bot.generar_respuesta('hola','507test',historial=history)
    assert 'saldo' in result
    assert 'Cuánto debo' in str(model.call_args.kwargs['messages'])
    assert 'Un saludo no borra' in str(model.call_args.kwargs['system'])
