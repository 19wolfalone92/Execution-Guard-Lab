import json, subprocess, sys, http.client
import pytest
from test_extended import CASES
from lab import TOOLS,call

@pytest.fixture(scope='module')
def server():
    p=subprocess.Popen([sys.executable,'-B','http_lab.py','--port','0'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        port=json.loads(p.stdout.readline())['port'];yield port
    finally:p.terminate();p.communicate(timeout=5)

def request(port,body=None,*,method='POST',path='/mcp',headers=None):
    c=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
    try:
        h={'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-11-25'}
        h.update(headers or {});c.request(method,path,body=json.dumps(body) if body is not None else None,headers=h)
        r=c.getresponse();data=r.read();return r.status,json.loads(data) if data else None
    finally:c.close()

def test_http_discovery(server):
    s,r=request(server,{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'qualification-http','version':'1'}}});assert s==200 and r['result']['protocolVersion']=='2025-11-25'
    assert request(server,{'jsonrpc':'2.0','method':'notifications/initialized'})==(202,None)
    s,r=request(server,{'jsonrpc':'2.0','id':2,'method':'tools/list'});assert s==200 and {t['name'] for t in r['result']['tools']}==set(TOOLS)
@pytest.mark.parametrize('name,args,key,expected',CASES,ids=[x[0] for x in CASES])
def test_http_calls(server,name,args,key,expected):
    payload={'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':name,'arguments':args}}
    s,r=request(server,payload);assert s==200 and r['result']['structuredContent']==call(name,args)
    assert request(server,payload)==(s,r)
@pytest.mark.parametrize('headers,status',[({'Origin':'https://untrusted.invalid'},403),({'Host':'untrusted.invalid'},403),({'MCP-Protocol-Version':'invalid'},400),({'Content-Type':'text/plain'},415),({'Accept':'text/plain'},406),({'Transfer-Encoding':'chunked'},400)])
def test_http_reject(server,headers,status):assert request(server,{'jsonrpc':'2.0','id':1,'method':'ping'},headers=headers)[0]==status

def test_http_limits(server):
    assert request(server,{'x':'x'*131073})[0]==413
    assert request(server,method='GET')[0]==405
    assert request(server,path='/other')[0]==404
    assert request(server,{'jsonrpc':'2.0','id':1,'method':'ping'})==(200,{'jsonrpc':'2.0','id':1,'result':{}})
