"""Synthetic, actual loopback TLS and ASGI negatives. No external credentials."""
import asyncio
import base64
import datetime as dt
import hashlib
import json
import os
import socket
import ssl
import subprocess
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from ipaddress import ip_address
from lab import MAX_LINE, call, TOOLS
from secure_http import LabApp,Settings,SCOPE,VERSION,META
from test_extended import CASES

BASE=Path(__file__).parent
ISS='https://issuer.example.invalid/'
SUB='synthetic-owner'; CLIENT='synthetic-client'; KID='fixture-1'
EVIDENCE=[]
EVIDENCE_LOCK=threading.Lock()

@pytest.fixture(scope='module',autouse=True)
def evidence_output():
    yield
    target=os.environ.get('LAB_TEST_EVIDENCE')
    if target:
        Path(target).write_text(json.dumps({'scope':'synthetic loopback HTTPS only; authorization header and JWT values excluded','records':EVIDENCE},ensure_ascii=False,indent=2),encoding='utf-8')

HEADERS={'Accept':'application/json, text/event-stream','Content-Type':'application/json','MCP-Protocol-Version':'2025-11-25'}

def req(method,params=None,rid=1):
    m={'jsonrpc':'2.0','method':method,'id':rid}
    if params is not None:m['params']=params
    return m

def init(version='2025-11-25'):
    return req('initialize',{'protocolVersion':version,'clientInfo':{'name':'eg-local-tls-probe','version':'1'},'capabilities':{}},'init')

@pytest.fixture(scope='module')
def keys():
    auth=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    return auth,other,auth.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)

def issue(key,resource,changes=None,headers=None):
    now=int(time.time())
    c={'iss':ISS,'sub':SUB,'aud':resource,'client_id':CLIENT,'scope':SCOPE,'iat':now-1,'exp':now+120}
    for k,v in (changes or {}).items():
        if v is None:c.pop(k,None)
        else:c[k]=v
    return jwt.encode(c,key,algorithm='RS256',headers={'kid':KID,'typ':'at+jwt',**(headers or {})})

@pytest.fixture(scope='module')
def tls_server(tmp_path_factory,keys):
    path=tmp_path_factory.mktemp('lab_tls'); auth,_,pub=keys
    tls=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'127.0.0.1')]);now=dt.datetime.now(dt.timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(tls.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-dt.timedelta(minutes=1)).not_valid_after(now+dt.timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address('127.0.0.1'))]),critical=False).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).sign(tls,hashes.SHA256()))
    (path/'tls.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (path/'tls.key').write_bytes(tls.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    (path/'auth.pem').write_bytes(pub)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    resource=f'https://127.0.0.1:{port}/mcp'
    env={**os.environ,'LAB_RESOURCE':resource,'LAB_ISSUER':ISS,'LAB_OWNER_SUB':SUB,'LAB_CLIENT_ID':CLIENT,'LAB_KEY_ID':KID,'LAB_PUBLIC_KEY_FILE':str(path/'auth.pem'),'LAB_TLS_CERT':str(path/'tls.crt'),'LAB_TLS_KEY':str(path/'tls.key'),'LAB_BIND':'127.0.0.1','LAB_PORT':str(port)}
    p=subprocess.Popen([sys.executable,'-B','run_local_tls_fixture.py'],cwd=BASE,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    context=ssl.create_default_context(cafile=str(path/'tls.crt'))
    try:
        for _ in range(100):
            if p.poll() is not None:raise AssertionError('TLS server exited: '+p.stderr.read()[:500])
            try:
                with httpx.Client(verify=context,trust_env=False,timeout=0.5) as c:
                    r=c.get(resource[:-4]+'/health')
                    if r.status_code==200:break
            except httpx.TransportError:pass
            time.sleep(.05)
        else:raise AssertionError('TLS readiness timed out')
        yield resource,context,issue(auth,resource),port
    finally:
        p.terminate()
        try:out,err=p.communicate(timeout=10)
        except subprocess.TimeoutExpired:p.kill();out,err=p.communicate()
        assert not out.strip(),out[:300]
        assert 'Traceback' not in err,err[:500]

def post(server,body,token=True,headers=None,raw=False):
    resource,context,good,_=server
    h={**HEADERS,**(headers or {})}
    if token is not False:h['Authorization']='Bearer '+(good if token is True else token)
    with httpx.Client(verify=context,trust_env=False,timeout=8,follow_redirects=False) as c:
        r=c.post(resource,content=body if raw else json.dumps(body).encode(),headers=h)
        if os.environ.get('LAB_TEST_EVIDENCE'):
            try: response=r.json() if r.content else None
            except ValueError: response={'body_sha256':hashlib.sha256(r.content).hexdigest()}
            record={'test':os.environ.get('PYTEST_CURRENT_TEST','').split(' (')[0], 'request':body if not raw else {'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()},'http_status':r.status_code,'response':response,'authenticated_fixture_supplied':token is not False}
            with EVIDENCE_LOCK:EVIDENCE.append(record)
        return r

@pytest.mark.parametrize('name,args,key,expected',CASES,ids=[x[0] for x in CASES])
def test_tls_all_tools(tls_server,name,args,key,expected):
    message=req('tools/call',{'name':name,'arguments':args},'tool-'+name)
    r=post(tls_server,message)
    assert r.status_code==200
    j=r.json(); assert j['id']==message['id'];result=j['result'];assert result['isError'] is False
    assert result['structuredContent']==call(name,args)
    assert json.loads(result['content'][0]['text'])==result['structuredContent']
    if isinstance(expected,(int,float)) and not isinstance(expected,bool):assert result['structuredContent'][key]==pytest.approx(expected,abs=1e-12)
    else:assert result['structuredContent'][key]==expected
    # Compare complete output against previously captured 0.2.0 RPC response, not just local 0.3 function.
    old=json.loads((BASE/'BASELINE_RERUN_RPC.json').read_text())['stdio']
    baseline=next(x['response']['result']['structuredContent'] for x in old if x['request'].get('params',{}).get('name')==name and x['request']['params']['arguments']==args)
    assert result['structuredContent']==baseline

@pytest.mark.parametrize('name,args,key,expected',CASES,ids=[x[0] for x in CASES])
def test_tls_all_invalid(tls_server,name,args,key,expected):
    r=post(tls_server,req('tools/call',{'name':name,'arguments':{}},2))
    assert r.status_code==200 and r.json()['result']['isError'] is True
    assert 'structuredContent' not in r.json()['result']

def test_discover_and_lifecycle(tls_server):
    resource,context,good,port=tls_server
    with httpx.Client(verify=context,trust_env=False) as c:
        h=c.get(resource[:-4]+'/health');assert h.json()=={'service':'execution-guard-lab','version':VERSION,'status':'online'}
        m=c.get(resource[:-4]+META);assert m.json()=={'resource':resource,'authorization_servers':[ISS],'scopes_supported':[SCOPE],'bearer_methods_supported':['header']}
        assert c.get(resource,headers={'Authorization':'Bearer '+good}).status_code==405
    with socket.create_connection(('127.0.0.1',port),timeout=4) as raw:
        with context.wrap_socket(raw,server_hostname='127.0.0.1') as tls:assert tls.version() in ('TLSv1.2','TLSv1.3')
    for version in ('2025-03-26','2025-06-18','2025-11-25','2026-07-28'):
        r=post(tls_server,init(version)); assert r.status_code==200
        j=r.json();assert j['id']=='init' and j['result']['serverInfo']['version']==VERSION
        assert j['result']['protocolVersion']==(version if version!='2026-07-28' else '2025-11-25')
    notification={'jsonrpc':'2.0','method':'notifications/initialized'}
    r=post(tls_server,notification);assert r.status_code==202 and r.content==b''
    r=post(tls_server,req('ping',rid='p'));assert r.json()=={'jsonrpc':'2.0','id':'p','result':{}}
    tools=post(tls_server,req('tools/list')).json()['result']['tools']
    assert len(tools)==23 and {t['name'] for t in tools}==set(TOOLS)
    for t in tools:
        spec=TOOLS[t['name']][0]; assert t['inputSchema']==spec['inputSchema'] and t['outputSchema']==spec['outputSchema']
        assert t['annotations']=={'readOnlyHint':True,'destructiveHint':False,'openWorldHint':False,'idempotentHint':True}
        assert t['securitySchemes']==[{'type':'oauth2','scopes':[SCOPE]}] and t['_meta']['securitySchemes']==t['securitySchemes']

@pytest.mark.parametrize('kind,expected',[('missing',401),('fake',401),('expired',401),('wrong_issuer',401),('wrong_audience',401),('wrong_owner',403),('wrong_client',403),('wrong_scope',403),('wrong_key',401),('wrong_kid',401),('wrong_type',401),('future_iat',401),('long_ttl',401),('missing_exp',401),('nbf',401),('array_aud',401),('bad_claim_type',401),('jku',401)])
def test_auth_negatives(tls_server,keys,kind,expected):
    resource=tls_server[0];auth,other,_=keys;now=int(time.time())
    changes={'expired':{'iat':now-100,'exp':now-10},'wrong_issuer':{'iss':'https://other.invalid'},'wrong_audience':{'aud':'https://other.invalid/mcp'},'wrong_owner':{'sub':'other'},'wrong_client':{'client_id':'other'},'wrong_scope':{'scope':'other'},'future_iat':{'iat':now+60},'long_ttl':{'exp':now+1800},'missing_exp':{'exp':None},'nbf':{'nbf':now+60},'array_aud':{'aud':[resource]},'bad_claim_type':{'iat':True}}.get(kind,{})
    hdr={'wrong_kid':{'kid':'other'},'wrong_type':{'typ':'JWT'},'jku':{'jku':'https://other.invalid/key'}}.get(kind,{})
    token= False if kind=='missing' else 'not-a-token' if kind=='fake' else issue(other if kind=='wrong_key' else auth,resource,changes,hdr)
    r=post(tls_server,req('tools/list'),token=token);assert r.status_code==expected and r.content==b''
    assert 'resource_metadata=' in r.headers['www-authenticate']

@pytest.mark.parametrize('body,status,code',[(b'{',400,-32700),(b'{"a":1,"a":2}',400,-32700),(b'{"a":NaN}',400,-32700),(b'{"a":1e999}',400,-32700),(b'{"a":"\\ud800"}',400,-32700),(b'\xff',400,-32700),(b'['*22+b'0'+b']'*22,400,-32700),(b'[]',200,-32600),(b'{"jsonrpc":"2.0","id":true,"method":"ping"}',200,-32600),(b'{"jsonrpc":"2.0","id":4,"method":"unknown"}',200,-32601),(b'{"jsonrpc":"2.0","id":5,"method":"initialize","params":{"protocolVersion":"2025-11-25"}}',200,-32602)])
def test_protocol_negatives(tls_server,body,status,code):
    r=post(tls_server,body,raw=True);assert r.status_code==status and r.json()['error']['code']==code

@pytest.mark.parametrize('headers,status',[({'Host':'evil.invalid'},403),({'Origin':'https://evil.invalid'},403),({'Origin':'null'},403),({'MCP-Protocol-Version':'bad'},400),({'Mcp-Session-Id':'unknown'},404),({'Content-Type':'text/plain'},415),({'Accept':'application/json'},406),({'Accept':'application/json;q=0, text/event-stream'},406)])
def test_transport_headers(tls_server,headers,status):
    assert post(tls_server,req('ping'),headers=headers).status_code==status

def test_oversize(tls_server):assert post(tls_server,b'x'*(MAX_LINE+1),raw=True).status_code==413

def test_unknown_tool(tls_server):
    r=post(tls_server,req('tools/call',{'name':'__unknown__','arguments':{}},123));assert r.json()['id']==123 and r.json()['result']['isError']

def test_parallel_and_reconnect(tls_server):
    def run(i):
        r=post(tls_server,req('tools/call',{'name':'math_calculate','arguments':{'operation':'multiply','a':i,'b':2}},f'p{i}'))
        assert r.status_code==200 and r.json()['id']==f'p{i}'
        return r.json()['result']['structuredContent']['result']
    for _ in range(2):
        with ThreadPoolExecutor(max_workers=4) as pool:assert list(pool.map(run,range(12)))==[i*2 for i in range(12)]
    assert post(tls_server,init()).status_code==200

def test_workflow_more_than_64_unknown():
    steps=[{'id':f's{i}','depends_on':[f'd{i}-{j}' for j in range(32)]} for i in range(32)]
    r=call('workflow_validate',{'steps':steps});assert not r['valid'] and len(r['unknown'])==1024

def test_config_fail_closed(keys):
    _,_,pub=keys
    with pytest.raises(ValueError):Settings('http://bad.invalid/mcp',ISS,SUB,CLIENT,KID,pub)
    with pytest.raises(ValueError):Settings('https://bad.invalid/mcp',ISS,SUB,CLIENT,KID,b'not-a-key')
    with pytest.raises(ValueError):Settings('https://bad.invalid/mcp',ISS,'',CLIENT,KID,pub)

async def asgi(app, *, message=None, events=None, scheme='https', headers=None):
    result=[]
    h=[(b'host',app.authority.encode()),(b'authorization',('Bearer '+message).encode()),(b'accept',b'application/json, text/event-stream'),(b'content-type',b'application/json')]+(headers or [])
    scope={'type':'http','scheme':scheme,'method':'POST','path':'/mcp','query_string':b'','headers':h}
    if events is None:
        data=json.dumps(req('ping')).encode()
        async def receive():return {'type':'http.request','body':data,'more_body':False}
    else:receive=events
    async def send(m):result.append(m)
    await app(scope,receive,send)
    return result

def test_asgi_limits(keys):
    auth,_,pub=keys;resource='https://lab.invalid/mcp';token=issue(auth,resource)
    async def run():
        app=LabApp(Settings(resource,ISS,SUB,CLIENT,KID,pub,requests_per_minute=2))
        for _ in range(2):assert (await asgi(app,message=token))[0]['status']==200
        assert (await asgi(app,message=token))[0]['status']==429
        app=LabApp(Settings(resource,ISS,SUB,CLIENT,KID,pub,max_parallel=1,body_timeout=.1))
        entered=asyncio.Event();release=asyncio.Event()
        async def pending():entered.set();await release.wait();return {'type':'http.request','body':json.dumps(req('ping')).encode(),'more_body':False}
        t=asyncio.create_task(asgi(app,message=token,events=pending));await entered.wait()
        assert (await asgi(app,message=token))[0]['status']==503
        release.set();assert (await t)[0]['status']==200
        async def slow():await asyncio.sleep(1)
        assert (await asgi(app,message=token,events=slow))[0]['status']==408
        async def disconnect():return {'type':'http.disconnect'}
        assert await asgi(app,message=token,events=disconnect)==[]
        assert app.active==0
        async def oversized():return {'type':'http.request','body':b'a'*(MAX_LINE+1),'more_body':False}
        assert (await asgi(app,message=token,events=oversized))[0]['status']==413
        assert (await asgi(app,message=token,scheme='http'))[0]['status']==403
        assert (await asgi(app,message=token,headers=[(b'host',b'other')]))[0]['status']==400
        assert (await asgi(app,message=token,headers=[(b'authorization',b'Bearer other')]))[0]['status']==400
        assert (await asgi(app,message=token))[0]['status']==200
    asyncio.run(run())

@pytest.mark.parametrize('bad_kind',['unsigned','noncanonical','duplicate_claim','deep_header'])
def test_extra_jwt_negatives(tls_server,keys,bad_kind):
    auth,_,_=keys;resource=tls_server[0];good=issue(auth,resource)
    a,b,c=good.split('.')
    if bad_kind=='unsigned':
        now=int(time.time());good=jwt.encode({'sub':SUB,'iat':now,'exp':now+60},key='',algorithm='none')
    elif bad_kind=='noncanonical':
        alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
        # RSA 2048 signature (256 bytes) uses 4 unused bits in final base64url symbol.
        assert alphabet.index(c[-1])%16==0
        good='.'.join([a,b,c[:-1]+alphabet[alphabet.index(c[-1])+1]])
    elif bad_kind=='duplicate_claim':
        raw=base64.urlsafe_b64decode(b+'='*(-len(b)%4))
        good='.'.join([a,base64.urlsafe_b64encode(raw[:-1]+b',"sub":"other"}').rstrip(b'=').decode(),c])
    else:
        good='.'.join([base64.urlsafe_b64encode(b'{"a":'+b'['*30+b'0'+b']'*30+b'}').rstrip(b'=').decode(),b,c])
    assert post(tls_server,req('ping'),token=good).status_code==401

def test_production_preflight_rejects_mismatched_runtime(monkeypatch):
    import production_preflight as p
    monkeypatch.setattr(p.md,'version',lambda name:'0.0.0')
    assert len(p.verify_runtime())==12
    with pytest.raises(SystemExit,match='PRODUCTION START BLOCKED'):p.require_runtime()
