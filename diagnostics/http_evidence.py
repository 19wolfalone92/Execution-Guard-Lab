"""One-shot, fail-closed diagnostic helper. Caller supplies a preauthorized URL.
No redirect following, no raw response text, header values or exception messages.
"""
from datetime import datetime, timezone
import hashlib, http.client, re, socket, ssl, urllib.error, urllib.request, uuid
from urllib.parse import urlsplit
MAX_BODY=4096
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

def classify(status):
    if status in (401,403): return 'authorization_denied'
    if 300<=status<400: return 'redirect'
    if status==429: return 'rate_limited'
    if status>=500: return 'server_error'
    if status>=400: return 'client_error'
    return 'unexpected_response'

def inspect_response(status, headers, body, expected):
    # The only retained body fragments are known synthetic markers. A hash is
    # deliberately omitted for unexpected data (which could contain credentials).
    result={'source_attribution':'UNVERIFIED','subsequent_operations':'STOP_UNLESS_EXPECTED','http':status,'category':classify(status),'body_bytes_sampled':len(body),'truncated':len(body)>MAX_BODY,'body_fragment':None,'retry_permitted':False}
    h=headers or {}
    ray=h.get('CF-Ray','')
    if re.fullmatch(r'[0-9a-fA-F]{16,32}(?:-[A-Z]{3})?',ray): result['cf_ray']=ray
    server=h.get('Server','').lower()
    if server in ('cloudflare','nginx','envoy','github.com'): result['server_class']=server
    ctype=h.get('Content-Type','').split(';')[0].strip().lower()
    if ctype in ('text/plain','text/html','application/json'): result['content_type']=ctype
    # These are bounded indicators, never proof of origin or cause.
    if status==403 and re.search(rb'(?i)\b(?:error|code)\s*[:#]?\s*1010\b',body[:MAX_BODY]):result['indicator']='body_mentions_1010'
    elif status in (401,403) and re.search(rb'(?i)cloudflare access',body[:MAX_BODY]):result['indicator']='body_mentions_access'
    retry=h.get('Retry-After','')
    if status==429 and re.fullmatch(r'[0-9]{1,6}',retry):result['retry_after_seconds']=int(retry)
    location=h.get('Location')
    if location:
        try:
            u=urlsplit(location); result['redirect']={'present':True,'scheme':u.scheme if u.scheme in ('http','https') else 'other','query_present':bool(u.query),'fragment_present':bool(u.fragment)}
        except ValueError: result['redirect']={'present':True,'malformed':True}
    if len(body)<=MAX_BODY and body==expected and status==200:
        result.update(category='expected_response',body_fragment=expected.decode('ascii'),status='PASS',subsequent_operations='EXPECTED_RESPONSE_ONLY')
    else: result['status']='BLOCKED' if status in (401,403) else 'FAIL'
    return result

def one_shot(url, expected, *, opener=None):
    if not re.fullmatch(rb'eglab-static-v[12]',expected): raise ValueError('only static markers allowed')
    identifier=uuid.uuid4().hex; base={'utc':datetime.now(timezone.utc).isoformat(),'operation':'GET','stage':'https_smoke','request_id':identifier}
    opener=opener or urllib.request.build_opener(NoRedirect())
    req=urllib.request.Request(url,headers={'Cache-Control':'no-cache','X-Lab-Diagnostic-ID':identifier})
    try:
        with opener.open(req,timeout=10) as r: row=inspect_response(r.status,r.headers,r.read(MAX_BODY+1),expected)
    except urllib.error.HTTPError as e:
        try: body=e.read(MAX_BODY+1)
        except Exception: body=b''
        row=inspect_response(e.code,e.headers,body,expected)
    except Exception as e:
        cause=e.reason if isinstance(e,urllib.error.URLError) else e
        category='tls_error' if isinstance(cause,ssl.SSLError) else 'dns_error' if isinstance(cause,socket.gaierror) else 'timeout' if isinstance(cause,TimeoutError) else 'transport_error'
        row={'category':category,'status':'FAIL','exception_type':type(cause).__name__ if type(cause).__name__ in ('SSLError','SSLCertVerificationError','gaierror','TimeoutError','ConnectionError','RemoteDisconnected') else 'other','retry_permitted':False}
    return {**base,**row}
