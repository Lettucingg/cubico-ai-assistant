import pytest
from app.services import business_location as loc
from app.ai import orchestrator as bot

@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setattr(loc.settings,'CUBICO_LOCAL_ADDRESS','Dirección vieja no verificada')
    monkeypatch.setattr(loc.settings,'CUBICO_LOCATION_URL','')
    monkeypatch.setattr(loc.settings,'CUBICO_LOCATION_VERIFIED',False)


def test_old_address_not_sufficient_and_no_inferred_landmarks():
    assert loc.verified_location() is None
    rules=loc.location_rules()
    assert 'NO VERIFICADA' in rules and 'Dirección vieja' not in rules
    assert 'ni digas que entre' in rules


def test_map_link_requires_explicit_confirmation_and_known_provider(monkeypatch):
    monkeypatch.setattr(loc.settings,'CUBICO_LOCATION_URL','https://maps.app.goo.gl/example-pin')
    assert loc.verified_location() is None
    monkeypatch.setattr(loc.settings,'CUBICO_LOCATION_VERIFIED',True)
    assert loc.verified_location()['enlace']=='https://maps.app.goo.gl/example-pin'
    for link in ['https://maps.app.goo.gl.evil.test/pin','http://maps.app.goo.gl/pin','https://user:pass@maps.app.goo.gl/pin','https://example.com/pin']:
        monkeypatch.setattr(loc.settings,'CUBICO_LOCATION_URL',link)
        assert loc.verified_location() is None


@pytest.mark.parametrize('text',['Mándame la ubicación porfa','Qué lugar están','Pero donde es','Es a un costado de Mimi','Momi','Dónde queda el local'])
def test_local_direction_queries(text):
    assert loc.location_question(text)


@pytest.mark.parametrize('text',['Dónde está mi paquete','Dame la ubicación de mi tracking','Dónde está mi carga','Cuál es la dirección de Miami','Dirección de China','Quiero abrir un casillero','Estoy en camino'])
def test_package_and_shipping_questions_not_mistaken_for_local(text):
    assert not loc.location_question(text)


def test_unknown_point_creates_real_escalation_without_model_guess(monkeypatch):
    changes=[]
    monkeypatch.setattr(bot,'actualizar_sesion',lambda phone,**kwargs:changes.append((phone,kwargs)))
    monkeypatch.setattr(bot,'call_anthropic',lambda *a,**k:pytest.fail('No debe inventar ubicaciones mediante el modelo'))
    text=bot.generar_respuesta('Mándame la ubicación porfa','507')
    assert 'equipo' in text and 'dirección vieja' not in text.lower()
    assert changes[0][1]['necesita_atencion_humana'] is True
    assert 'pin vigente' in changes[0][1]['motivo_escalamiento']


def test_short_followup_does_not_confirm_arrival_from_old_history(monkeypatch):
    monkeypatch.setattr(bot,'actualizar_sesion',lambda *a,**k:None)
    monkeypatch.setattr(bot,'call_anthropic',lambda *a,**k:pytest.fail('No debe confirmar llegada'))
    assert 'equipo' in bot.generar_respuesta('Estoy aquí','507',historial=[{'role':'user','content':'Dónde queda el local'},{'role':'assistant','content':'Al lado de Momi, entra.'}])


def test_verified_pin_is_sent_exactly_without_extra_landmarks(monkeypatch):
    monkeypatch.setattr(loc.settings,'CUBICO_LOCATION_VERIFIED',True)
    monkeypatch.setattr(loc.settings,'CUBICO_LOCATION_URL','https://maps.app.goo.gl/example-pin')
    monkeypatch.setattr(bot,'active_context',lambda *a:[])
    monkeypatch.setattr(bot,'call_anthropic',lambda *a,**k:pytest.fail('No necesita adivinar rutas'))
    text=bot.generar_respuesta('Qué lugar están','507')
    assert 'https://maps.app.goo.gl/example-pin' in text
    assert 'cerca de El Dorado' not in text
