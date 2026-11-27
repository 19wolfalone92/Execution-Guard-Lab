"""One static lab Worker, account-bound, no bindings, no production MCP.
No external dependency, no redirects, no secrets in logs. No retries on writes.
Only run in the expressly authorized laboratory workflow.
"""
import datetime as dt, hashlib, json, os, re, secrets, sys, time, urllib.error, urllib.request, uuid
from pathlib import Path
from diagnostics.http_evidence import MAX_BODY, inspect_response

class Stop(Exception): pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None
opener=urllib.request.build_opener(NoRedirect())
report={'scope':'isolated static Worker write test; not MCP', 'steps':[], 'status':'PARTIAL'}

def record(label, **fields):
    row={'step':label,**fields}; report['steps'].append(row); print(json.dumps(row),flush=True)

def require(ok,label):
    if not ok: raise Stop(label)

def main():
    token=os.environ.get('CF_TOKEN','').strip(); account=os.environ.get('CF_ACCOUNT','').strip().lower()
    run=os.environ.get('GITHUB_RUN_ID',''); attempt=os.environ.get('GITHUB_RUN_ATTEMPT','')
    require(bool(token) and bool(re.fullmatch(r'[0-9a-f]{32}',account)),'credentials missing or invalid')
    require(os.environ.get('GITHUB_REPOSITORY')=='19wolfalone92/Execution-Guard-Lab' and os.environ.get('GITHUB_REF')=='refs/heads/qualification/cloud-runtime-oauth-20261127','repository or ref mismatch')
    require(bool(re.fullmatch(r'\d{1,20}',run)) and bool(re.fullmatch(r'\d{1,4}',attempt)),'run id invalid')
    name=f'eglab-probe-{run}-{attempt}'; report.update(worker=name,github_sha=os.environ.get('GITHUB_SHA'),run_id=run)
    prefix='/accounts/'+account; script=prefix+'/workers/scripts/'+name
    def api(label,path,method='GET',data=None,ctype='application/json'):
        require(path.startswith(prefix+'/') or path==prefix or path in ('/accounts?per_page=50','/user/tokens/verify'),'out of scope path')
        allowed_writes={('PUT',script),('POST',script+'/subdomain'),('POST',script+'/deployments'),('DELETE',script)}
        if method!='GET': require((method,path) in allowed_writes,'out of scope write')
        h={'Authorization':'Bearer '+token,'Accept':'application/json'}
        if data is not None: h['Content-Type']=ctype
        if isinstance(data,dict): data=json.dumps(data).encode()
        req=urllib.request.Request('https://api.cloudflare.com/client/v4'+path,data=data,headers=h,method=method)
        started=time.perf_counter_ns(); request_id=uuid.uuid4().hex
        try:
            with opener.open(req,timeout=20) as res:
                status=res.status; body=json.loads(res.read(2_000_001))
        except urllib.error.HTTPError as e:
            raw=b''
            try: raw=e.read(MAX_BODY+1)
            except Exception: pass
            codes=[]
            try:
                payload=json.loads(raw[:MAX_BODY])
                codes=[x['code'] for x in payload.get('errors',[]) if isinstance(x.get('code'),int)]
            except Exception: pass
            evidence=inspect_response(e.code,e.headers,raw,b'',request_id=request_id,
                utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                duration_ms=(time.perf_counter_ns()-started)/1_000_000)
            keep=('category','cf_ray','server_header','server_class','content_type',
                  'cloudflare_error_code','cloudflare_error_code_source','indicator',
                  'body_fragment','body_bytes_sampled','truncated','retry_after_seconds',
                  'stop_reason','duration_ms')
            safe={k:evidence[k] for k in keep if k in evidence}
            record(label,status='FAIL',http=e.code,codes=codes,request_id=request_id,**safe)
            raise Stop('API rejected '+label) from None
        except Exception as e:
            record(label,status='UNVERIFIED',error=type(e).__name__,
                   request_id=request_id,
                   duration_ms=round((time.perf_counter_ns()-started)/1_000_000,3))
            raise Stop('API transport '+label) from None
        require(isinstance(body,dict) and body.get('success') is True,'API unsuccessful '+label)
        record(label,status='PASS',http=status,request_id=request_id,
               duration_ms=round((time.perf_counter_ns()-started)/1_000_000,3))
        return body
    verified=api('token_active',prefix+'/tokens/verify' if token.startswith('cfat_') else '/user/tokens/verify')['result']
    require(verified.get('status')=='active','inactive token')
    expiry=dt.datetime.fromisoformat(verified['expires_on'].replace('Z','+00:00'))
    require(0<(expiry-dt.datetime.now(dt.timezone.utc)).total_seconds()<=31*86400,'expiry not bounded')
    acct=api('account_match',prefix)['result']; require(str(acct.get('id','')).lower()==account,'account mismatch')
    accounts=api('single_visible_account','/accounts?per_page=50'); info=accounts.get('result_info',{}); visible=accounts['result']
    require(info.get('total_count')==1 and info.get('total_pages')==1 and len(visible)==1 and str(visible[0].get('id','')).lower()==account,'account isolation read guard failed')
    record('account_guard',status='PASS',expiry_utc=expiry.isoformat(),visible_accounts=1,policy_basis='owner attestation and effective read only; exact policy not independently readable')
    workers=api('existing_worker_list',prefix+'/workers/scripts')['result']; require(isinstance(workers,list) and all(isinstance(w,dict) for w in workers),'worker list invalid')
    require(not any(w.get('id')==name or w.get('name')==name for w in workers),'worker name collision')
    sub=api('existing_account_subdomain',prefix+'/workers/subdomain')['result'].get('subdomain','')
    require(bool(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',sub)),'no existing workers.dev subdomain')
    url=f'https://{name}.{sub}.workers.dev/health'; report['test_url']=url
    def upload(marker):
        source=('export default {fetch(request){const u=new URL(request.url);return request.method==="GET"&&u.pathname==="/health"?new Response('+json.dumps(marker)+',{headers:{"Cache-Control":"no-store","Content-Type":"text/plain"}}):new Response("Not found",{status:404});}};\n').encode()
        boundary='eglab'+secrets.token_hex(16)
        meta=json.dumps({'main_module':'worker.mjs','compatibility_date':'2026-11-26','bindings':[]}).encode()
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n'.encode()+meta+f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="worker.mjs"; filename="worker.mjs"\r\nContent-Type: application/javascript+module\r\n\r\n'.encode()+source+f'\r\n--{boundary}--\r\n'.encode())
        api('upload_'+marker,script,'PUT',body,'multipart/form-data; boundary='+boundary)
        record('source_hash_'+marker,sha256=hashlib.sha256(source).hexdigest())
    def active(label):
        d=api(label,script+'/deployments')['result']['deployments'][0]; versions=d['versions']
        require(len(versions)==1 and versions[0]['percentage']==100,'deployment not single version')
        vid=str(uuid.UUID(versions[0]['version_id'])); did=str(uuid.UUID(d['id']))
        report['deployment_id']=did; report['version_id']=vid
        record('active_version',phase=label,version_id=vid,deployment_id=did); return vid
    def smoke(marker):
        from diagnostics.http_evidence import one_shot
        result=one_shot(url,marker.encode('ascii'),opener=opener,context={
            'worker_identifier':report.get('worker'),'deployment_id':report.get('deployment_id'),
            'version_id':report.get('version_id'),'source_sha':report.get('github_sha')})
        record('https_'+marker,**result)
        require(result['status']=='PASS','HTTPS authorization rejected' if result['status']=='BLOCKED' else 'HTTPS verification failed')
    upload_attempted=False; subdomain_disabled_confirmed=False; cleanup_failures=[]
    first='eglab-static-v1'; second='eglab-static-v2'
    try:
        upload_attempted=True
        upload(first); report['created']=True
        # Verify settings can be read; do not log arbitrary account metadata.
        settings=api('read_settings',script+'/settings')['result']; require(isinstance(settings,dict),'settings invalid')
        v1=active('deployment_v1')
        state=api('enable_test_subdomain',script+'/subdomain','POST',{'enabled':True,'previews_enabled':False})['result']
        require(state.get('enabled') is True,'subdomain not enabled')
        smoke(first)
        upload(second); v2=active('deployment_v2'); require(v2!=v1,'version did not change'); smoke(second)
        api('rollback',script+'/deployments','POST',{'strategy':'percentage','versions':[{'version_id':v1,'percentage':100}]})
        require(active('deployment_rollback')==v1,'rollback mismatch'); smoke(first)
        state=api('disable_test_subdomain',script+'/subdomain','POST',{'enabled':False,'previews_enabled':False})['result']
        require(state.get('enabled') is False,'disable not confirmed')
        readback=api('verify_disabled',script+'/subdomain')['result']; require(readback.get('enabled') is False,'disable readback failed')
        subdomain_disabled_confirmed=True
        report['status']='PASS'; report['public_test_endpoint_disabled']=True
    finally:
        # Resolve ambiguous upload outcomes by reading back only the collision-checked Worker name.
        if upload_attempted:
            try:
                current=api('cleanup_find_worker',prefix+'/workers/scripts')['result']
                require(isinstance(current,list),'cleanup worker list invalid')
                exists=any(w.get('id')==name or w.get('name')==name for w in current)
                if exists:
                    if not subdomain_disabled_confirmed:
                        state=api('cleanup_disable_subdomain',script+'/subdomain','POST',
                            {'enabled':False,'previews_enabled':False})['result']
                        require(state.get('enabled') is False,'cleanup disable not confirmed')
                        report['public_test_endpoint_disabled']=True
                    api('cleanup_delete_worker',script,'DELETE')
                    remaining=api('cleanup_verify_worker_absent',prefix+'/workers/scripts')['result']
                    require(isinstance(remaining,list) and not any(
                        w.get('id')==name or w.get('name')==name for w in remaining
                    ),'cleanup worker still present')
                    report['worker_deleted']=True
                    record('cleanup_delete_worker',status='PASS')
                else:
                    report['worker_deleted']=False
                    record('cleanup_worker_absent',status='PASS')
            except Exception as error:
                cleanup_failures.append('worker_cleanup')
                record('cleanup_worker',status='FAIL',error=type(error).__name__)
        report['cleanup_status']='PARTIAL' if cleanup_failures else 'PASS'
        if cleanup_failures:
            report['cleanup_failures']=cleanup_failures
            if report.get('status')=='PASS': report['status']='PARTIAL'

if __name__=='__main__':
    # Cloud lifecycle remains explicitly held. The callable is retained for
    # isolated mocks only; authorized recovery requires a reviewed new release.
    print('HOLD: original HTTPS denial unresolved; no cloud operations performed')
    sys.exit(1)
