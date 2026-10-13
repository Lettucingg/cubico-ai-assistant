from types import SimpleNamespace as NS
from app.ai import orchestrator as bot


def setup_model(monkeypatch, record):
    captured=[]
    monkeypatch.setattr(bot,'obtener_nombre_completo_cliente',lambda *a:record)
    monkeypatch.setattr(bot,'obtener_oportunidad_comercial_abierta',lambda *a:None)
    monkeypatch.setattr(bot,'active_context',lambda *a:[])
    def model(*args,**kwargs):
        captured.append(kwargs)
        return NS(stop_reason='end_turn',content=[NS(type='text',text='No hay problema. Cualquier cosa me avisas.')])
    monkeypatch.setattr(bot,'call_anthropic',model)
    return captured


def test_verified_recipient_is_explicit_even_after_wrong_prior_name(monkeypatch):
    calls=setup_model(monkeypatch,{'encontrado':True,'nombre_completo':'María Pérez'})
    history=[{'role':'humano','operador':'alexander','autor_tipo':'humano','content':'Te explico lo de verificar.'},
             {'role':'assistant','content':'No hay problema, Alexander.'}]
    bot.generar_respuesta('Listo disculpas','507',codigo_cliente='CBC-1',historial=history)
    prompt=calls[0]['messages'][-1]['content']
    assert 'NOMBRE DEL REGISTRO VERIFICADO' in prompt and 'María Pérez' in prompt
    assert 'no lo sustituyas por el nombre de un operador' in prompt
    assert 'enviado por alexander' not in str(calls)
    assert history[0]['operador']=='alexander' # History and panel authorship remain intact.


def test_without_verified_name_does_not_guess_from_operator(monkeypatch):
    calls=setup_model(monkeypatch,{'encontrado':False})
    bot.generar_respuesta('Listo disculpas','507',historial=[{'role':'humano','operador':'luis','content':'Ya lo revisamos.'}])
    prompt=calls[0]['messages'][-1]['content']
    assert 'Responde sin nombre' in prompt
    assert 'herramienta de verificación confirme su nombre' in prompt
    assert 'enviado por luis' not in str(calls)


def test_real_client_can_be_named_alexander(monkeypatch):
    calls=setup_model(monkeypatch,{'encontrado':True,'nombre_completo':'Alexander Rodríguez'})
    bot.generar_respuesta('Listo disculpas','507',codigo_cliente='CBC-1')
    assert 'Alexander Rodríguez' in calls[0]['messages'][-1]['content']


def test_client_messages_preserved_and_staff_signature_disambiguated():
    original=[{'role':'user','content':'Me llamo Teresa'}, {'role':'humano','operador':'alexander','content':'Soy Alexander del equipo, ya revisamos el caso.'}]
    normalized=bot.normalizar_historial_para_claude(original)
    assert normalized[0]['content']=='Me llamo Teresa'
    assert 'no por Bruno ni por el cliente' in normalized[1]['content']
    assert 'El autor o su firma no identifican al cliente' in normalized[1]['content']
    assert original[1]['operador']=='alexander'
