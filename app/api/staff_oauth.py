"""Browser consent and SDK-managed OAuth routes for Claude's Sign in now flow."""
import json
import secrets
from html import escape
from datetime import timedelta
from urllib.parse import urlencode
from pydantic import AnyHttpUrl
from sqlalchemy import update, delete
from sqlalchemy.exc import IntegrityError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Route
from mcp.server.auth.routes import create_auth_routes, build_metadata
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.server.auth.provider import construct_redirect_uri
from app.db.session_store import SessionSesiones, OAuthRegistroPanel
from app.services import staff_oauth as service, ai_connections

COOKIE = '__Secure-cubico-ia-csrf'
OPTIONS = ClientRegistrationOptions(enabled=True, valid_scopes=[service.SCOPE], default_scopes=[service.SCOPE])
META = build_metadata(AnyHttpUrl(service.ISSUER), None, OPTIONS, RevocationOptions()).model_dump(mode='json', exclude_none=True)
META['token_endpoint_auth_methods_supported'] = ['none', 'client_secret_post', 'client_secret_basic']
LABELS = {'conversaciones':'Conversaciones y tracking público', 'cuentas':'Saldos, facturas y paquetes del cliente verificado', 'incidencias':'Incidencias, seguimiento y capturas', 'operacion':'Ubicación confirmada y situación operativa'}


def page(nonce, csrf, data, message='', status=200):
    review = data.get('phase') == 'review'
    identity = data.get('identity', {})
    if review:
        fields = '<input type="hidden" name="revision" value="'+escape(data['review_nonce'],quote=True)+'"><h2>Revisa el acceso</h2><p>Usuario: <strong>'+escape(identity['usuario'])+'</strong></p><p>Conexión personal: <strong>'+escape(identity['nombre'])+'</strong></p><ul>'+''.join('<li>'+escape(LABELS[s])+'</li>' for s in identity['permisos'])+'</ul><p>Estos datos se compartirán con la cuenta de Claude desde la que abriste la conexión. Claude podrá consultarlos y preparar respuestas. Los mensajes se revisan y envían desde Cúbico.</p><label class="check"><input name="consentimiento" type="checkbox" value="si" required> Autorizo este acceso con los permisos indicados.</label><button type="submit" name="accion" value="autorizar">Autorizar a Claude</button>'
    else:
        fields = '<h2>Conecta tu Claude</h2><p>Usa la clave personal que creaste en <strong>Configuración → Mi conexión con Claude</strong>. Puedes pegar el valor completo que empieza por Bearer.</p><label>Clave personal de Cúbico<input type="password" name="clave" required maxlength="200" autocomplete="off" placeholder="Pega tu clave de conexión"></label><p class="small">No necesitas tu contraseña de Claude ni una clave API de Anthropic.</p><button type="submit" name="accion" value="revisar">Revisar permisos</button>'
    body = '<!doctype html><html lang="es"><meta charset="utf-8"><meta name="referrer" content="same-origin"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Autorizar Claude · Cúbico</title><style> *{box-sizing:border-box}body{margin:0;padding:calc(24px + env(safe-area-inset-top,0px)) 16px calc(24px + env(safe-area-inset-bottom,0px));font:16px system-ui;background:#f6f4ee;color:#171714;line-height:1.6}main{max-width:520px;margin:4vh auto;background:white;border:1px solid #e5e1d6;border-radius:20px;padding:28px;box-shadow:0 10px 36px #1717140b}h1{font-size:22px;margin:0 0 20px}h2{font-size:20px;margin:0 0 12px}label{display:block;font-weight:600}input[type=password]{display:block;width:100%;font:inherit;padding:13px;border:1px solid #d8d3c7;border-radius:12px;margin:8px 0}button{font:inherit;min-height:46px;border:1px solid #ddd7c9;border-radius:12px;padding:10px 18px;cursor:pointer;margin-top:16px;width:100%;background:#171714;color:white}.cancel{background:white;color:#65532c}.small{font-size:13px;color:#777}.check{display:flex;align-items:flex-start;gap:10px;font-size:14px}.check input{margin-top:6px;flex:none;width:18px;height:18px}.error{padding:12px;background:#fff1ed;color:#923b2d;border-radius:12px}ul{padding-left:22px}a{color:#806325}</style><main><h1>Cúbico · Conexión con Claude</h1>'
    if message:
        body += '<p class="error" role="alert">'+escape(message)+'</p>'
    body += '<form method="post" action="'+service.ISSUER+'/consentir"><input type="hidden" name="solicitud" value="'+escape(nonce, quote=True)+'"><input type="hidden" name="csrf" value="'+escape(csrf, quote=True)+'">'+fields+'<button type="submit" class="cancel" name="accion" value="cancelar" formnovalidate>Cancelar conexión</button></form><p class="small">Puedes revocar el acceso desde Cúbico. La autorización vence cuando vence la conexión personal.</p></main></html>'
    return HTMLResponse(body, status_code=status, headers={'Cache-Control':'no-store', 'Referrer-Policy':'same-origin', 'X-Frame-Options':'DENY', 'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https://claude.ai/api/mcp/auth_callback https://claude.com/api/mcp/auth_callback; frame-ancestors 'none'; base-uri 'none'"})


async def metadata(request):
    return JSONResponse(META, headers={'Cache-Control':'public, max-age=60', 'Access-Control-Allow-Origin':'*'})


async def resource_metadata(request):
    return JSONResponse({'resource': service.RESOURCE, 'authorization_servers':[service.ISSUER], 'scopes_supported':[service.SCOPE], 'bearer_methods_supported':['header'], 'resource_name':'Cúbico · Consultas del equipo'}, headers={'Cache-Control':'public, max-age=60', 'Access-Control-Allow-Origin':'*'})


def expired():
    return HTMLResponse('<!doctype html><meta charset="utf-8"><p>Esta solicitud venció o ya se utilizó. Vuelve a Claude y pulsa conectar de nuevo.</p>',status_code=400,headers={'Cache-Control':'no-store', 'Referrer-Policy':'no-referrer'})


async def consent(request: Request):
    if request.method == 'GET':
        nonce = request.query_params.get('solicitud', '')
        csrf = secrets.token_urlsafe(32)
        with SessionSesiones() as db:
            row = service._get(db, 'pending', nonce)
            if not row:
                return expired()
            data = json.loads(row.contenido)
            # Opening/reopening requires a fresh explicit authentication, never auto-consent.
            data.pop('identity', None); data.pop('parent', None);data['phase']='login';data['csrf']=service.digest(csrf)
            row.contenido=json.dumps(data);db.commit()
        response=page(nonce,csrf,data)
        response.set_cookie(COOKIE,csrf,max_age=600,secure=True,httponly=True,samesite='lax',path='/panel/ia/oauth')
        return response
    if request.headers.get('origin') != service.ORIGIN:
        return HTMLResponse('Origen no permitido',status_code=403)
    form=await request.form()
    nonce=str(form.get('solicitud',''));csrf=str(form.get('csrf',''));action=str(form.get('accion',''))
    with SessionSesiones() as db:
        row=service._get(db,'pending',nonce)
        if not row:
            return expired()
        data=json.loads(row.contenido)
        if not csrf or not secrets.compare_digest(csrf,request.cookies.get(COOKIE,'')) or not secrets.compare_digest(service.digest(csrf),data.get('csrf','')):
            return HTMLResponse('Solicitud de autorización no válida. Abre la conexión desde Claude de nuevo.',status_code=403,headers={'Cache-Control':'no-store'})
        if action=='cancelar':
            db.delete(row);db.commit()
            return RedirectResponse(construct_redirect_uri(data['params']['redirect_uri'],error='access_denied',state=data['params']['state']),status_code=303,headers={'Referrer-Policy':'no-referrer'})
        if action=='revisar':
            if row.intentos>=6:
                return page(nonce,csrf,data,'Demasiados intentos. Abre una nueva solicitud desde Claude.',429)
            db.execute(update(OAuthRegistroPanel).where(OAuthRegistroPanel.clave==row.clave).values(intentos=OAuthRegistroPanel.intentos+1));db.commit()
            raw=str(form.get('clave','')).strip()
            if raw.lower().startswith('bearer '):raw=raw[7:].strip()
            from app.api.panel import USUARIOS_PANEL
            actor=ai_connections.authenticate(raw,USUARIOS_PANEL) if raw.startswith('cubico_') else None
            if not actor:
                data.pop('identity',None);data.pop('parent',None);data['phase']='login'
                row=db.get(OAuthRegistroPanel,row.clave);row.contenido=json.dumps(data);db.commit()
                return page(nonce,csrf,data,'La clave no es válida, está vencida o fue revocada. Revisa tu conexión en Cúbico.',400)
            connection=service.parent(db,actor['id'])
            if connection is None:
                return page(nonce,csrf,{'phase':'login'},'La conexión dejó de estar activa. Crea una nueva desde Cúbico.',400)
            data['phase']='review';data['parent']=connection.id;data['review_nonce']=secrets.token_urlsafe(24)
            data['identity']={'usuario':actor['usuario'],'nombre':connection.nombre,'permisos':actor['permisos']}
            row=db.get(OAuthRegistroPanel,row.clave);row.contenido=json.dumps(data);db.commit()
            return page(nonce,csrf,data)
        if action!='autorizar' or data.get('phase')!='review' or form.get('consentimiento')!='si' or not secrets.compare_digest(str(form.get('revision','')),data.get('review_nonce','invalid')):
            return page(nonce,csrf,data,'Primero revisa los permisos y confirma la autorización.',400)
        connection=service.parent(db,data['parent'])
        if not connection or json.loads(connection.permisos)!=data['identity']['permisos']:
            return page(nonce,csrf,{'phase':'login'},'La conexión personal cambió o dejó de estar activa. Inicia de nuevo.',400)
        # One-time CAS: concurrent consent submissions cannot mint two authorization codes.
        consumed=db.execute(delete(OAuthRegistroPanel).where(OAuthRegistroPanel.clave==row.clave,OAuthRegistroPanel.contenido==row.contenido)).rowcount
        if consumed!=1:return expired()
        code=secrets.token_urlsafe(32)
        service._put(db,'code',code,{'parent':connection.id,'client_id':data['client_id'],'params':data['params']},service.now()+timedelta(minutes=3));db.commit()
    response=RedirectResponse(construct_redirect_uri(data['params']['redirect_uri'],code=code,state=data['params']['state']),status_code=303,headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
    response.delete_cookie(COOKIE,path='/panel/ia/oauth',secure=True,httponly=True,samesite='lax')
    return response


class OAuthLimits:
    """Bound unauthenticated request sizes and per-source rates across workers."""
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        if len(scope.get('query_string',b''))>8192:
            return await JSONResponse({'error':'invalid_request'},status_code=414)(scope,receive,send)
        if scope.get('method')=='POST':
            ip=(scope.get('client') or ('unknown',))[0];minute=__import__('time').time_ns()//60_000_000_000
            group='register' if scope.get('path','').endswith('/register') else 'other'
            rate_key=service.key('rate',f'{ip}:{minute}:{group}');limit=10 if group=='register' else 60
            allowed=False
            for attempt in range(2):
                with SessionSesiones() as db:
                    row=db.get(OAuthRegistroPanel,rate_key)
                    if row is None:
                        service._cleanup(db)
                        db.add(OAuthRegistroPanel(clave=rate_key,tipo='rate',contenido='{}',vence_en=service.now()+timedelta(minutes=2),intentos=1))
                        try:db.commit();allowed=True;break
                        except IntegrityError:db.rollback();continue
                    allowed=db.execute(update(OAuthRegistroPanel).where(OAuthRegistroPanel.clave==rate_key,OAuthRegistroPanel.intentos<limit).values(intentos=OAuthRegistroPanel.intentos+1)).rowcount==1;db.commit();break
            if not allowed:return await JSONResponse({'error':'temporarily_unavailable'},status_code=429,headers={'Retry-After':'60'})(scope,receive,send)
        # Read the bounded body before invoking Starlette so a size rejection never follows a started response.
        buffered=[];count=0
        if scope.get('method')=='POST':
            while True:
                message=await receive();buffered.append(message)
                if message['type']=='http.disconnect':break
                count+=len(message.get('body',b''))
                if count>16384:return await JSONResponse({'error':'invalid_request'},status_code=413)(scope,receive,send)
                if not message.get('more_body',False):break
        async def replay():
            if buffered:return buffered.pop(0)
            return await receive()
        await self.app(scope,replay,send)



routes=create_auth_routes(service.provider,AnyHttpUrl(service.ISSUER),client_registration_options=OPTIONS)
# Add public-client auth metadata without changing the SDK's grant/PKCE handlers.
routes=[r for r in routes if r.path!='/.well-known/oauth-authorization-server']
routes.extend([Route('/.well-known/oauth-authorization-server',metadata,methods=['GET','OPTIONS']),Route('/recurso',resource_metadata,methods=['GET','OPTIONS']),Route('/consentir',consent,methods=['GET','POST'])])
oauth_app=OAuthLimits(Starlette(routes=routes))
