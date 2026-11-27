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

@pytest.mark.parametrize('status,body,headers,indicator',[
(403,b'<html>Cloudflare Error 1010</html>',{'Server':'cloudflare'},'body_mentions_1010'),
(403,b'Cloudflare Access',{'Server':'cloudflare'},'body_mentions_access'),
(403,b'proxy refused',{'Server':'nginx'},None),
(403,b'worker says no',{},None),
(403,b'Error 1010 forged by upstream',{},'body_mentions_1010'),
(429,b'wait',{'Retry-After':'60'},None),
(403,b'credential-DO-NOT-LOG',{},None)])
def test_ambiguous_source(status,body,headers,indicator):
    from diagnostics.http_evidence import inspect_response
    r=inspect_response(status,headers,body,MARK)
    assert r.get('indicator')==indicator and r['source_attribution']=='UNVERIFIED'
    assert r['subsequent_operations']=='STOP_UNLESS_EXPECTED' and not r['retry_permitted']
    assert 'credential-DO-NOT-LOG' not in json.dumps(r)
    if status==429:assert r['retry_after_seconds']==60


def test_1010_captures_allowlisted_evidence_and_never_raw_body():
    import io
    from diagnostics.http_evidence import one_shot
    headers=Message()
    headers['CF-Ray']='0123456789abcdef-AMS'
    headers['Server']='cloudflare'
    headers['Content-Type']='text/html; charset=utf-8'
    headers['CF-Error-Type']='1010'
    headers['CF-Error-Origin']='security'
    headers['Set-Cookie']='credential-DO-NOT-LOG'
    headers['Location']='https://hidden.invalid/path?token=credential-DO-NOT-LOG'
    body=(b'<html>Cloudflare Error 1010. The owner of this website has banned your access '
          b'based on your browser signature. Authorization: Bearer secret-value '
          b'credential-DO-NOT-LOG</html>')
    class EvidenceFake:
        calls=0
        request=None
        timeout=None
        def open(self,request,timeout):
            self.calls+=1; self.request=request; self.timeout=timeout
            raise urllib.error.HTTPError(URL,403,'credential-DO-NOT-LOG',headers,io.BytesIO(body))
    fake=EvidenceFake()
    context={
        'worker_identifier':'eglab-probe-459-1',
        'deployment_id':'01234567-89ab-4cde-8fab-0123456789ab',
        'version_id':'11234567-89ab-4cde-8fab-0123456789ab',
        'source_sha':'a'*40
    }
    result=one_shot(URL,MARK,opener=fake,context=context)
    assert fake.calls==1 and fake.timeout==10
    assert fake.request.get_header('User-agent') == 'ExecutionGuardLab/0.9.0'
    assert result['user_agent'] == 'ExecutionGuardLab/0.9.0'
    assert result['http_status']==403 and result['status']=='BLOCKED'
    assert result['cloudflare_error_code']==1010
    assert result['cloudflare_error_code_source']=='response_body_unverified'
    assert result['body_fragment']=='Cloudflare Error 1010'
    assert result['cf_ray']=='0123456789abcdef-AMS'
    assert result['cf_error_type']=='1010' and result['cf_error_origin']=='security'
    assert result['server_header']=='cloudflare' and result['content_type']=='text/html'
    assert result['worker_identifier']==context['worker_identifier']
    assert result['deployment_id']==context['deployment_id']
    assert result['version_id']==context['version_id'] and result['source_sha']==context['source_sha']
    assert result['request_id']==result['request_correlation_id']
    assert result['duration_ms']>=0 and result['stop_reason']=='http_403'
    assert result['source_attribution']=='UNVERIFIED' and not result['retry_permitted']
    serialized=json.dumps(result)
    for forbidden in ('credential-DO-NOT-LOG','secret-value','hidden.invalid','Authorization','Set-Cookie'):
        assert forbidden not in serialized


def test_invalid_context_metadata_is_omitted():
    from diagnostics.http_evidence import inspect_response
    result=inspect_response(403,{'Server':'cloudflare'},b'Cloudflare Error 1010',MARK,context={
        'worker_identifier':'bad worker','deployment_id':'not-a-uuid','version_id':'secret',
        'source_sha':'z'*40
    })
    assert 'worker_identifier' not in result and 'deployment_id' not in result
    assert 'version_id' not in result and 'source_sha' not in result
    assert result['cloudflare_error_code']==1010
    assert result['source_attribution']=='UNVERIFIED'
