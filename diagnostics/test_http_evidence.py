import io, json, socket, ssl, urllib.error
from email.message import Message
import pytest
from diagnostics.http_evidence import one_shot, MAX_BODY
URL='https://synthetic.invalid/health'; MARK=b'eglab-static-v1'
class Reply(io.BytesIO):
    def __init__(self,status,body,headers): super().__init__(body); self.status=status; self.headers=headers
class Fake:
    def __init__(self,status=200,body=MARK,exception=None): self.status=status;self.body=body;self.exception=exception;self.calls=0
    def open(self,request,timeout):
        self.calls+=1
        if self.exception: raise self.exception
        h=Message();h['CF-Ray']='0123456789abcdef-AMS';h['Server']='cloudflare';h['Content-Type']='text/plain';h['Set-Cookie']='credential-DO-NOT-LOG';h['Location']='https://hidden.invalid/path?secret=credential-DO-NOT-LOG'
        if self.status>=300: raise urllib.error.HTTPError(URL,self.status,'credential-DO-NOT-LOG',h,io.BytesIO(self.body))
        return Reply(self.status,self.body,h)
@pytest.mark.parametrize('status',[200,301,302,400,401,403,404,429,500,502,503])
def test_http(status):
    f=Fake(status,MARK if status==200 else b'credential-DO-NOT-LOG');r=one_shot(URL,MARK,opener=f)
    assert f.calls==1 and r['http']==status and r['cf_ray']=='0123456789abcdef-AMS' and not r['retry_permitted']
    assert r['status']==('PASS' if status==200 else 'BLOCKED' if status in (401,403) else 'FAIL')
    assert 'credential-DO-NOT-LOG' not in json.dumps(r) and 'hidden.invalid' not in json.dumps(r)
@pytest.mark.parametrize('exc,category',[(TimeoutError(),'timeout'),(socket.gaierror(),'dns_error'),(ssl.SSLError(),'tls_error')])
def test_network(exc,category):
    f=Fake(exception=urllib.error.URLError(exc));r=one_shot(URL,MARK,opener=f);assert r['category']==category and f.calls==1
@pytest.mark.parametrize('body',[b'\xff\xfe',b'x'*(MAX_BODY+10)])
def test_bad_body(body):
    f=Fake(body=body);r=one_shot(URL,MARK,opener=f);assert r['status']=='FAIL' and r['body_fragment'] is None and f.calls==1
