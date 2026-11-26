"""Lab 0.3.0: bounded stateless MCP over TLS, external OAuth resource server.
No authorization server, token issuance, outbound requests, persistent task state,
or execution of input. Deployment requires an owner-managed OAuth issuer.
"""
from __future__ import annotations
import asyncio
import base64
import copy
import json
import os
import re
import ssl
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from lab import MAX_LINE, TOOLS, decode, rpc

VERSION = '0.3.0'
VERSIONS = frozenset(('2025-03-26','2025-06-18','2025-11-25'))
SCOPE = 'lab:read'
MAX_RESPONSE = 1024 * 1024
META = '/.well-known/oauth-protected-resource/mcp'


def https_url(value, *, resource=False):
    p = urlsplit(value)
    if (not value.isascii() or p.scheme != 'https' or not p.hostname or p.username or p.password or
        p.query or p.fragment or any(c in value for c in '\r\n\t "\\') or
        (resource and p.path != '/mcp')):
        raise ValueError('invalid_https_configuration')
    # Reject invalid port, noncanonical case and ambiguous host formatting.
    _ = p.port
    if p.netloc != p.netloc.lower():
        raise ValueError('noncanonical_authority')
    return p


@dataclass(frozen=True)
class Settings:
    resource: str
    issuer: str
    subject: str
    client_id: str
    kid: str
    public_key_pem: bytes
    requests_per_minute: int = 180
    max_parallel: int = 4
    body_timeout: float = 5.0

    def __post_init__(self):
        https_url(self.resource, resource=True)
        https_url(self.issuer)
        for v in (self.subject, self.client_id, self.kid):
            if not isinstance(v, str) or not v or len(v)>512 or any(ord(c)<32 for c in v):
                raise ValueError('invalid_identity_configuration')
        if not 1<=self.requests_per_minute<=600 or not 1<=self.max_parallel<=8 or not 0.05<=self.body_timeout<=15:
            raise ValueError('invalid_resource_limits')
        key=serialization.load_pem_public_key(self.public_key_pem)
        if not isinstance(key, rsa.RSAPublicKey) or not 2048<=key.key_size<=4096:
            raise ValueError('invalid_rsa_verification_key')

    @classmethod
    def from_env(cls):
        return cls(os.environ['LAB_RESOURCE'], os.environ['LAB_ISSUER'],
                   os.environ['LAB_OWNER_SUB'], os.environ['LAB_CLIENT_ID'],
                   os.environ['LAB_KEY_ID'], Path(os.environ['LAB_PUBLIC_KEY_FILE']).read_bytes())


class LabApp:
    def __init__(self, config: Settings):
        self.cfg = config
        self.key = serialization.load_pem_public_key(config.public_key_pem)
        self.authority = urlsplit(config.resource).netloc
        self.origin = 'https://' + self.authority
        self.allowed_origins = {self.origin, 'https://chatgpt.com', 'https://www.chatgpt.com'}
        self.challenge = f'Bearer resource_metadata="{self.origin}{META}", scope="{SCOPE}"'
        self.recent = deque()
        self.active = 0

    def token_status(self, auth):
        if not auth or len(auth)>8192 or not auth.startswith('Bearer '):
            return 401
        token=auth[7:]
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',token):
            return 401
        try:
            # Reject duplicate JSON keys and malformed claims before cryptographic validation.
            head, body, signature = token.split('.')
            def unpack_segment(s):
                raw=base64.urlsafe_b64decode(s+'='*(-len(s)%4))
                if base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')!=s:raise ValueError('noncanonical_token')
                return raw
            header, claims = decode(unpack_segment(head)), decode(unpack_segment(body))
            unpack_segment(signature)
            if not isinstance(header,dict) or not isinstance(claims,dict):return 401
            if header.get('alg')!='RS256' or header.get('kid')!=self.cfg.kid or header.get('typ','').lower() not in ('at+jwt','application/at+jwt'):
                return 401
            if any(k in header for k in ('jku','jwk','x5u','x5c','crit')):return 401
            for k in ('exp','iat','nbf'):
                if (k!='nbf' or k in claims) and type(claims.get(k)) is not int:return 401
            claims=jwt.decode(token,self.key,algorithms=['RS256'],audience=self.cfg.resource,
                              issuer=self.cfg.issuer,options={'require':['exp','iat','iss','aud','sub','client_id','scope'],'strict_aud':True},leeway=0)
            if not 0<claims['exp']-claims['iat']<=900:return 401
            if claims['sub']!=self.cfg.subject or claims['client_id']!=self.cfg.client_id:return 403
            if not isinstance(claims['scope'],str) or set(claims['scope'].split())!={SCOPE}:return 403
            return 200
        except (jwt.PyJWTError,ValueError,TypeError,AttributeError,OverflowError,RecursionError):
            return 401

    def rate_ok(self):
        now=time.monotonic()
        while self.recent and self.recent[0]<=now-60:self.recent.popleft()
        if len(self.recent)>=self.cfg.requests_per_minute:return False
        self.recent.append(now);return True

    def mcp(self,req):
        if isinstance(req,dict) and req.get('jsonrpc')=='2.0' and req.get('method')=='initialize' and type(req.get('id')) in (int,str):
            p=req.get('params')
            if not isinstance(p,dict) or not isinstance(p.get('capabilities'),dict) or not isinstance(p.get('clientInfo'),dict) or not all(isinstance(p['clientInfo'].get(k),str) and p['clientInfo'][k] for k in ('name','version')):
                rid=req['id'] if type(req['id']) in (int,str) else None
                return {'jsonrpc':'2.0','id':rid,'error':{'code':-32602,'message':'invalid_initialize_parameters'}}
        result=rpc(req)
        if result is None:return None
        if isinstance(req,dict) and 'result' in result:
            if req.get('method')=='initialize':result['result']['serverInfo']['version']=VERSION
            if req.get('method')=='tools/list':
                tools=copy.deepcopy(result['result']['tools'])
                for t in tools:
                    security=[{'type':'oauth2','scopes':[SCOPE]}]
                    t['securitySchemes']=security;t['_meta']={'securitySchemes':security}
                result['result']['tools']=tools
        return result

    async def __call__(self,scope,receive,send):
        if scope['type']=='lifespan':
            while True:
                message=await receive()
                if message['type']=='lifespan.startup':await send({'type':'lifespan.startup.complete'})
                elif message['type']=='lifespan.shutdown':
                    await send({'type':'lifespan.shutdown.complete'});return
        if scope['type']!='http':return
        async def reply(status,body=None,extra=()):
            raw=b'' if body is None else json.dumps(body,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode('utf-8')
            if len(raw)>MAX_RESPONSE:
                status=500;raw=b'{"error":"response_limit"}'
            headers=[(b'cache-control',b'no-store'),(b'x-content-type-options',b'nosniff'),(b'content-length',str(len(raw)).encode())]
            if body is not None:headers.append((b'content-type',b'application/json'))
            headers.extend(extra)
            await send({'type':'http.response.start','status':status,'headers':headers})
            await send({'type':'http.response.body','body':raw})
        h={}
        for key,value in scope.get('headers',[]):
            k=key.decode('latin-1').lower();h.setdefault(k,[]).append(value.decode('latin-1'))
        singular=('host','origin','authorization','content-length','content-type','mcp-protocol-version','mcp-session-id','transfer-encoding')
        if any(len(h.get(k,[]))>1 for k in singular):return await reply(400)
        get=lambda k: h.get(k,[None])[0]
        if scope.get('scheme')!='https' or get('host')!=self.authority:return await reply(403)
        if get('origin') is not None and get('origin') not in self.allowed_origins:return await reply(403)
        if scope.get('query_string'):return await reply(400)
        if not self.rate_ok():return await reply(429,extra=((b'retry-after',b'60'),))
        method=scope['method'];path=scope['path']
        if path in (META,'/.well-known/oauth-protected-resource','/health','/version'):
            if method!='GET':return await reply(405,extra=((b'allow',b'GET'),))
            if path in (META,'/.well-known/oauth-protected-resource'):
                return await reply(200,{'resource':self.cfg.resource,'authorization_servers':[self.cfg.issuer],'scopes_supported':[SCOPE],'bearer_methods_supported':['header']})
            return await reply(200,{'service':'execution-guard-lab','version':VERSION,'status':'online'})
        if path!='/mcp':return await reply(404)
        auth=self.token_status(get('authorization'))
        if auth!=200:
            challenge=self.challenge+(', error="insufficient_scope"' if auth==403 else '')
            return await reply(auth,extra=((b'www-authenticate',challenge.encode('ascii')),))
        if method!='POST':return await reply(405,extra=((b'allow',b'POST'),))
        if get('mcp-session-id') is not None:return await reply(404)
        version=get('mcp-protocol-version')
        if version is not None and version not in VERSIONS:return await reply(400)
        if get('transfer-encoding') and get('content-length'):return await reply(400)
        length=get('content-length')
        if length is not None:
            if not re.fullmatch(r'[0-9]{1,8}',length):return await reply(400)
            if int(length)>MAX_LINE:return await reply(413)
        if (get('content-type') or '').split(';',1)[0].strip().lower()!='application/json':return await reply(415)
        accept=set()
        for entry in ','.join(h.get('accept',[])).split(','):
            parts=[p.strip().lower() for p in entry.split(';')]
            try:
                quality=next((float(p[2:]) for p in parts[1:] if p.startswith('q=')),1)
                if 0<quality<=1:accept.add(parts[0])
            except ValueError:pass
        if not {'application/json','text/event-stream'}<=accept:return await reply(406)
        if self.active>=self.cfg.max_parallel:return await reply(503,extra=((b'retry-after',b'1'),))
        self.active+=1
        try:
            data=bytearray()
            try:
                async with asyncio.timeout(self.cfg.body_timeout):
                    while True:
                        msg=await receive()
                        if msg['type']=='http.disconnect':return
                        if msg['type']!='http.request':return await reply(400)
                        chunk=msg.get('body',b'')
                        if len(data)+len(chunk)>MAX_LINE:return await reply(413)
                        data.extend(chunk)
                        if not msg.get('more_body'):break
            except TimeoutError:return await reply(408)
            if length is not None and len(data)!=int(length):return await reply(400)
            try:request=decode(bytes(data))
            except (ValueError,UnicodeError,RecursionError):
                return await reply(400,{'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'invalid_json'}})
            task=asyncio.create_task(asyncio.to_thread(self.mcp,request))
            try:response=await asyncio.shield(task)
            except asyncio.CancelledError:
                await task;raise
            except Exception:
                return await reply(500,{'error':'internal_error'})
            return await reply(202 if response is None else 200,response)
        finally:self.active-=1


def run_tls_server(cfg,cert,key,bind,port):
    import uvicorn
    # Refuse startup without TLS material. No plain HTTP public mode.
    tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.minimum_version=ssl.TLSVersion.TLSv1_2;tls.load_cert_chain(cert,key)
    uvicorn.run(LabApp(cfg),host=bind,port=port,
                ssl_certfile=cert,ssl_keyfile=key,ssl_version=ssl.PROTOCOL_TLS_SERVER,
                proxy_headers=False,access_log=False,workers=1,limit_concurrency=24,http='h11',ws='none',
                timeout_keep_alive=5,timeout_graceful_shutdown=10,log_level='warning')

def main():
    from production_preflight import require_runtime
    require_runtime()
    cfg=Settings.from_env()
    cert=os.environ['LAB_TLS_CERT']; key=os.environ['LAB_TLS_KEY']
    run_tls_server(cfg,cert,key,os.getenv('LAB_BIND','127.0.0.1'),int(os.getenv('LAB_PORT','8443')))

if __name__=='__main__':main()
