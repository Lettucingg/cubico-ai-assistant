"""OAuth authorization-code + PKCE adapter for personal panel connections.

MCP's official SDK validates protocol, clients, redirect bindings and PKCE.
This provider persists single-use grants and rotating token families. The
operator's existing personal connection remains the revocable permission root.
"""
import base64
import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet
from sqlalchemy import select, delete, func
from mcp.server.auth.provider import AccessToken, AuthorizationCode, RefreshToken, RegistrationError, AuthorizeError, TokenError
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from app.core.config import settings
from app.db.session_store import OAuthRegistroPanel, ConexionIAPanel, SessionSesiones

ORIGIN = 'https://bot.cubico.com.pa'
ISSUER = ORIGIN + '/panel/ia/oauth'
RESOURCE = ORIGIN + '/mcp/'
METADATA_URL = ISSUER + '/recurso'
CALLBACKS = {'https://claude.ai/api/mcp/auth_callback', 'https://claude.com/api/mcp/auth_callback'}
SCOPE = 'mcp:tools'


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def key(kind, raw):
    return kind + ':' + digest(raw)


def _cipher():
    # Existing server-side secret; never sent to clients. A rotation requires re-registering OAuth clients.
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(('cubico-oauth-clients-v1:' + settings.CUBICO_NOTIFY_KEY).encode()).digest()))


def _put(db, kind, raw, data, expiry):
    db.add(OAuthRegistroPanel(clave=key(kind, raw), tipo=kind, contenido=json.dumps(data, ensure_ascii=False), vence_en=expiry, intentos=0))


def _get(db, kind, raw):
    if not raw or len(raw) > 500:
        return None
    row = db.get(OAuthRegistroPanel, key(kind, raw))
    return row if row and row.vence_en > now() else None


def _cleanup(db):
    db.execute(delete(OAuthRegistroPanel).where(OAuthRegistroPanel.vence_en <= now()))


def parent(db, parent_id):
    from app.api.panel import USUARIOS_PANEL
    row = db.get(ConexionIAPanel, parent_id)
    if not row or row.revocado or row.vence_en <= now() or row.usuario not in USUARIOS_PANEL:
        return None
    return row


def actor_for_token(token):
    """OAuth tokens cannot outlive or widen the originating personal connection."""
    with SessionSesiones() as db:
        row = _get(db, 'access', token)
        if not row:
            return None
        data = json.loads(row.contenido)
        connection = parent(db, data['parent'])
        if connection is None or data.get('resource') != RESOURCE:
            return None
        return {'id': connection.id, 'usuario': connection.usuario, 'permisos': json.loads(connection.permisos)}


class CubicoOAuthProvider:
    async def get_client(self, client_id):
        with SessionSesiones() as db:
            row = _get(db, 'client', client_id)
            if not row:
                return None
            data = json.loads(row.contenido)
            encrypted = data.pop('_secret_encrypted', None)
            if encrypted:
                try:
                    data['client_secret'] = _cipher().decrypt(encrypted.encode()).decode()
                except Exception:
                    return None
            return OAuthClientInformationFull.model_validate(data)

    async def register_client(self, client_info):
        if not client_info.redirect_uris or len(client_info.redirect_uris) > 4 or any(str(uri) not in CALLBACKS for uri in client_info.redirect_uris):
            raise RegistrationError(error='invalid_redirect_uri', error_description='Solo se admiten los callbacks HTTPS de Claude.')
        if client_info.scope and set(client_info.scope.split()) != {SCOPE}:
            raise RegistrationError(error='invalid_client_metadata', error_description='Permiso OAuth no admitido.')
        if client_info.token_endpoint_auth_method not in {'none', 'client_secret_post', 'client_secret_basic'}:
            raise RegistrationError(error='invalid_client_metadata', error_description='Método de cliente no admitido.')
        data = client_info.model_dump(mode='json')
        secret = data.pop('client_secret', None)
        if secret:
            data['_secret_encrypted'] = _cipher().encrypt(secret.encode()).decode()
        with SessionSesiones() as db:
            _cleanup(db)
            if db.scalar(select(func.count()).select_from(OAuthRegistroPanel).where(OAuthRegistroPanel.tipo == 'client')) >= 2000:
                raise RegistrationError(error='invalid_client_metadata', error_description='Límite temporal de registros.')
            _put(db, 'client', client_info.client_id, data, now()+timedelta(days=180))
            db.commit()

    async def authorize(self, client, params):
        if str(params.redirect_uri) not in CALLBACKS or params.resource not in (None, RESOURCE, RESOURCE.rstrip('/')):
            raise AuthorizeError(error='invalid_request', error_description='Destino o recurso no admitido.')
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', params.code_challenge) or set(params.scopes or [SCOPE]) != {SCOPE}:
            raise AuthorizeError(error='invalid_request', error_description='Usa PKCE S256 y el permiso mcp:tools.')
        nonce = secrets.token_urlsafe(32)
        data = {'client_id': client.client_id, 'params': params.model_dump(mode='json'), 'phase': 'login'}
        with SessionSesiones() as db:
            _cleanup(db); _put(db, 'pending', nonce, data, now()+timedelta(minutes=10)); db.commit()
        return ISSUER + '/consentir?solicitud=' + nonce

    async def load_authorization_code(self, client, authorization_code):
        with SessionSesiones() as db:
            row = _get(db, 'code', authorization_code)
            if not row:
                return None
            data = json.loads(row.contenido)
            if data['client_id'] != client.client_id or parent(db, data['parent']) is None:
                return None
            return AuthorizationCode(code=authorization_code, scopes=[SCOPE], expires_at=row.vence_en.replace(tzinfo=timezone.utc).timestamp(), client_id=client.client_id, code_challenge=data['params']['code_challenge'], redirect_uri=data['params']['redirect_uri'], redirect_uri_provided_explicitly=data['params']['redirect_uri_provided_explicitly'], resource=RESOURCE)

    def _pair(self, db, client_id, parent_id, family, scopes):
        root = parent(db, parent_id)
        if root is None:
            raise TokenError(error='invalid_grant', error_description='La conexión personal dejó de estar activa.')
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        expiry = min(root.vence_en, now()+timedelta(hours=1))
        data = {'client_id': client_id, 'parent': root.id, 'family': family, 'scopes': scopes, 'resource': RESOURCE}
        _put(db, 'access', access, data, expiry)
        _put(db, 'refresh', refresh, data, root.vence_en)
        return OAuthToken(access_token=access, token_type='Bearer', expires_in=max(1, int((expiry-now()).total_seconds())), refresh_token=refresh, scope=' '.join(scopes))

    async def exchange_authorization_code(self, client, authorization_code):
        with SessionSesiones() as db:
            row = _get(db, 'code', authorization_code.code)
            if not row:
                raise TokenError(error='invalid_grant', error_description='Código vencido o ya utilizado.')
            data = json.loads(row.contenido)
            if data['client_id'] != client.client_id:
                raise TokenError(error='invalid_grant', error_description='Cliente no válido.')
            used = db.execute(delete(OAuthRegistroPanel).where(OAuthRegistroPanel.clave == row.clave, OAuthRegistroPanel.vence_en > now())).rowcount
            if used != 1:
                raise TokenError(error='invalid_grant', error_description='Código ya utilizado.')
            tokens = self._pair(db, client.client_id, data['parent'], secrets.token_hex(16), [SCOPE])
            db.commit()
            return tokens

    async def load_refresh_token(self, client, refresh_token):
        with SessionSesiones() as db:
            row = _get(db, 'refresh', refresh_token)
            if not row:
                return None
            data = json.loads(row.contenido)
            if data['client_id'] != client.client_id or parent(db, data['parent']) is None:
                return None
            return RefreshToken(token=refresh_token, client_id=client.client_id, scopes=data['scopes'], expires_at=int(row.vence_en.replace(tzinfo=timezone.utc).timestamp()))

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        if set(scopes) != {SCOPE}:
            raise TokenError(error='invalid_scope', error_description='No se pueden ampliar permisos.')
        with SessionSesiones() as db:
            row = _get(db, 'refresh', refresh_token.token)
            if not row:
                raise TokenError(error='invalid_grant', error_description='Renovación vencida o ya utilizada.')
            data = json.loads(row.contenido)
            if data['client_id'] != client.client_id:
                raise TokenError(error='invalid_grant', error_description='Cliente no válido.')
            used = db.execute(delete(OAuthRegistroPanel).where(OAuthRegistroPanel.clave == row.clave, OAuthRegistroPanel.vence_en > now())).rowcount
            if used != 1:
                raise TokenError(error='invalid_grant', error_description='Renovación ya utilizada.')
            self._revoke_family(db, data['family'])
            tokens = self._pair(db, client.client_id, data['parent'], data['family'], scopes)
            db.commit()
            return tokens

    def _revoke_family(self, db, family):
        for row in db.scalars(select(OAuthRegistroPanel).where(OAuthRegistroPanel.tipo.in_(['access', 'refresh']))).all():
            if json.loads(row.contenido).get('family') == family:
                db.delete(row)

    async def load_access_token(self, token):
        actor = actor_for_token(token)
        if not actor:
            return None
        with SessionSesiones() as db:
            row = _get(db, 'access', token)
            if not row:
                return None
            data = json.loads(row.contenido)
            return AccessToken(token=token, client_id=data['client_id'], scopes=data['scopes'], expires_at=int(row.vence_en.replace(tzinfo=timezone.utc).timestamp()), resource=RESOURCE, subject=actor['usuario'])

    async def revoke_token(self, token):
        with SessionSesiones() as db:
            for kind in ('access', 'refresh'):
                row = _get(db, kind, token.token)
                if row:
                    self._revoke_family(db, json.loads(row.contenido)['family'])
                    db.commit()
                    return


provider = CubicoOAuthProvider()
