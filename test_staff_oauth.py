"""End-to-end SDK OAuth tests using real HTTP handlers, PKCE and permission-root revocation."""
import asyncio
import base64
import hashlib
import json
import re
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from urllib.parse import urlparse,parse_qs
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from app.api import staff_oauth as web, staff_mcp, panel
from app.services import staff_oauth as service, ai_connections, incidents
from app.db import session_store

CALLBACK='https://claude.ai/api/mcp/auth_callback'
ORIGIN=service.ORIGIN


@pytest.fixture
def setup(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    session_store.BaseSesiones.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    for module in (service,web,ai_connections,staff_mcp,incidents):monkeypatch.setattr(module,'SessionSesiones',factory)
    monkeypatch.setattr(panel,'USUARIOS_PANEL',{'alexander':'test','luis':'test'})
    server=FastMCP('qa',stateless_http=True,json_response=True,streamable_http_path='/',transport_security=TransportSecuritySettings(allowed_hosts=['bot.cubico.com.pa'],allowed_origins=[ORIGIN]))
    @server.tool()
    def permisos_actuales():return staff_mcp.require('incidencias','qa')
    mcp_app=staff_mcp.PersonalConnectionAuth(server.streamable_http_app())
    @asynccontextmanager
    async def lifespan(app):
        async with server.session_manager.run():yield
    app=FastAPI(lifespan=lifespan);app.mount('/panel/ia/oauth',web.oauth_app);app.mount('/mcp',mcp_app)
    app.add_route('/.well-known/oauth-authorization-server/panel/ia/oauth',web.metadata)
    app.add_route('/.well-known/oauth-protected-resource/mcp',web.resource_metadata)
    with TestClient(app,base_url=ORIGIN,follow_redirects=False) as client:yield client,factory


def register(c,method='none',**extra):
    result=c.post('/panel/ia/oauth/register',json={'redirect_uris':[CALLBACK],'token_endpoint_auth_method':method,'grant_types':['authorization_code','refresh_token'],'response_types':['code'],'client_name':'Claude',**extra})
    assert result.status_code==201,result.text
    return result.json()


def begin(c,client,**extra):
    verifier=secrets.token_urlsafe(48)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    params={'response_type':'code','client_id':client['client_id'],'redirect_uri':CALLBACK,'code_challenge':challenge,'code_challenge_method':'S256','scope':'mcp:tools','state':'state-proof','resource':service.RESOURCE,**extra}
    result=c.get('/panel/ia/oauth/authorize',params=params)
    assert result.status_code==302,result.text
    login=c.get(result.headers['location'])
    assert login.status_code==200,login.text
    fields={name:re.search(r'name="'+name+r'" value="([^"]*)"',login.text).group(1) for name in ('solicitud','csrf')}
    return verifier,fields,login


def review(c,fields,personal):
    result=c.post('/panel/ia/oauth/consentir',data={**fields,'accion':'revisar','clave':'Bearer '+personal['token']},headers={'Origin':ORIGIN})
    assert result.status_code==200,result.text
    revision=re.search('name="revision" value="([^"]*)"',result.text).group(1)
    return {**fields,'revision':revision},result


def confirm(c,fields):
    result=c.post('/panel/ia/oauth/consentir',data={**fields,'accion':'autorizar','consentimiento':'si'},headers={'Origin':ORIGIN})
    assert result.status_code==303,result.text
    parsed=parse_qs(urlparse(result.headers['location']).query)
    assert parsed['state']==['state-proof'] and result.headers['location'].startswith(CALLBACK+'?')
    return parsed['code'][0]


def exchange(c,client,code,verifier,**extra):
    data={'grant_type':'authorization_code','client_id':client['client_id'],'code':code,'redirect_uri':CALLBACK,'code_verifier':verifier,**extra}
    if client.get('client_secret'):data['client_secret']=client['client_secret']
    return c.post('/panel/ia/oauth/token',data=data)


def tools(c,token):
    return c.post('/mcp/',headers={'Authorization':'Bearer '+token,'Accept':'application/json, text/event-stream'},json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'permisos_actuales','arguments':{}}})


@pytest.mark.parametrize('auth_method',['none','client_secret_post'])
def test_full_oauth_pkce_refresh_and_revocation(setup,auth_method):
    c,db=setup;client=register(c,auth_method)
    personal=ai_connections.issue('alexander','Mi Claude',['incidencias'])
    verifier,fields,login=begin(c,client)
    assert 'Clave personal' in login.text and 'frame-ancestors' in login.headers['content-security-policy']
    assert login.headers['referrer-policy']=='same-origin'
    for callback in service.CALLBACKS:
        assert callback in login.headers['content-security-policy']
    assert '<meta name="referrer" content="same-origin">' in login.text
    assert c.cookies.get(web.COOKIE)
    assert c.post('/panel/ia/oauth/consentir',data={**fields,'accion':'revisar','clave':personal['token']}).status_code==403
    fields,review_page=review(c,fields,personal)
    assert 'alexander' in review_page.text and 'Incidencias' in review_page.text and personal['token'] not in review_page.text
    assert 'Saldos, facturas' not in review_page.text
    assert c.post('/panel/ia/oauth/consentir',data={**fields,'accion':'autorizar'},headers={'Origin':ORIGIN}).status_code==400
    code=confirm(c,fields)
    assert exchange(c,client,code,'wrong').status_code==400
    assert exchange(c,client,code,verifier,redirect_uri='https://claude.com/api/mcp/auth_callback').status_code==400
    response=exchange(c,client,code,verifier)
    assert response.status_code==200,response.text
    token=response.json();assert response.headers['cache-control']=='no-store'
    assert exchange(c,client,code,verifier).status_code==400
    result=tools(c,token['access_token'])
    assert result.status_code==200 and 'alexander' in result.text and 'incidencias' in result.text
    assert ai_connections.authenticate(token['access_token'],{'luis':'test'}) is None
    data={'grant_type':'refresh_token','client_id':client['client_id'],'refresh_token':token['refresh_token']}
    if client.get('client_secret'):data['client_secret']=client['client_secret']
    assert c.post('/panel/ia/oauth/token',data={**data,'scope':'admin'}).status_code==400
    refreshed=c.post('/panel/ia/oauth/token',data=data)
    assert refreshed.status_code==200,refreshed.text
    new=refreshed.json()
    assert new['access_token']!=token['access_token'] and new['refresh_token']!=token['refresh_token']
    assert tools(c,token['access_token']).status_code==401
    assert c.post('/panel/ia/oauth/token',data=data).status_code==400
    assert tools(c,new['access_token']).status_code==200
    with db() as s:
        content=' '.join(r.contenido for r in s.scalars(select(session_store.OAuthRegistroPanel)))
        for secret in [personal['token'],code,new['access_token'],new['refresh_token'],client.get('client_secret')]:
            if secret:assert secret not in content
    ai_connections.revoke('alexander',personal['id'])
    assert tools(c,new['access_token']).status_code==401
    assert c.post('/panel/ia/oauth/token',data={**data,'refresh_token':new['refresh_token']}).status_code==400


def test_metadata_redirect_rejection_body_limits_and_pkce(setup):
    c,_=setup
    challenge=c.post('/mcp/',json={})
    assert service.METADATA_URL in challenge.headers['www-authenticate']
    resource=c.get('/panel/ia/oauth/recurso').json();assert resource['resource']==service.RESOURCE and resource['authorization_servers']==[service.ISSUER]
    meta=c.get('/.well-known/oauth-authorization-server/panel/ia/oauth').json()
    assert meta['code_challenge_methods_supported']==['S256'] and 'register' in meta['registration_endpoint']
    for uri in ['https://evil.invalid/callback',CALLBACK+'.evil','http://claude.ai/api/mcp/auth_callback',CALLBACK+'?evil=1']:
        result=c.post('/panel/ia/oauth/register',json={'redirect_uris':[uri],'grant_types':['authorization_code','refresh_token']})
        assert result.status_code==400
    assert c.post('/panel/ia/oauth/register',content='x'*17000).status_code==413
    client=register(c)
    r=c.get('/panel/ia/oauth/authorize',params={'response_type':'code','client_id':client['client_id'],'redirect_uri':CALLBACK,'code_challenge':'x'*43,'code_challenge_method':'plain'})
    assert r.status_code==400 or 'error=' in r.headers.get('location','')


def test_personal_identity_review_csrf_snapshot_and_cancel(setup):
    c,db=setup;client=register(c)
    a=ai_connections.issue('alexander','A',['incidencias']);b=ai_connections.issue('luis','B',['conversaciones','operacion'])
    _,fields,_=begin(c,client)
    f1,p1=review(c,fields,a);f2,p2=review(c,fields,b)
    assert 'luis' in p2.text and 'alexander' not in p2.text
    bad=c.post('/panel/ia/oauth/consentir',data={**f1,'accion':'autorizar','consentimiento':'si'},headers={'Origin':ORIGIN})
    assert bad.status_code==400
    wrong=c.post('/panel/ia/oauth/consentir',data={**f2,'csrf':'wrong','accion':'autorizar','consentimiento':'si'},headers={'Origin':ORIGIN})
    assert wrong.status_code==403
    result=c.post('/panel/ia/oauth/consentir',data={**f2,'accion':'cancelar'},headers={'Origin':ORIGIN})
    assert result.status_code==303 and 'access_denied' in result.headers['location']
    assert c.get('/panel/ia/oauth/consentir',params={'solicitud':fields['solicitud']}).status_code==400
    _,fields,_=begin(c,client)
    ai_connections.revoke('alexander',a['id'])
    assert c.post('/panel/ia/oauth/consentir',data={**fields,'accion':'revisar','clave':a['token']},headers={'Origin':ORIGIN}).status_code==400


def test_expired_pending_and_failed_attempt_limit(setup):
    c,db=setup;client=register(c);_,fields,_=begin(c,client)
    for _ in range(6):assert c.post('/panel/ia/oauth/consentir',data={**fields,'accion':'revisar','clave':'cubico_wrong'},headers={'Origin':ORIGIN}).status_code==400
    assert c.post('/panel/ia/oauth/consentir',data={**fields,'accion':'revisar','clave':'cubico_wrong'},headers={'Origin':ORIGIN}).status_code==429
    with db() as s:
        row=s.get(session_store.OAuthRegistroPanel,service.key('pending',fields['solicitud']));row.vence_en=service.now()-timedelta(seconds=1);s.commit()
    assert c.get('/panel/ia/oauth/consentir',params={'solicitud':fields['solicitud']}).status_code==400
