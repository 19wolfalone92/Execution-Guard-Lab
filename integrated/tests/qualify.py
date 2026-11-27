"""Local-only full chain. Browser simulated; official SDK calls real Python Worker."""
import asyncio, hashlib, base64, json, secrets, ssl, sys, time
from pathlib import Path
from urllib.parse import urlencode,urlsplit,parse_qs
import httpx2
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from sdk_probe_v2 import fixtures,sdk_imports
ISSUER='https://127.0.0.1:8790';RESOURCE=ISSUER+'/mcp'; REDIRECT='https://client.example.invalid/callback';HEADERS={'Accept':'application/json, text/event-stream'}
async def main(cert):
    Client,transport,_=sdk_imports();rows=[];checks=[];tls=ssl.create_default_context(cafile=cert)
    async with httpx2.AsyncClient(verify=tls,trust_env=False,follow_redirects=False,timeout=30) as browser:
        async def expect(name,condition):
            assert condition,name;checks.append(name)
        r=await browser.post(RESOURCE,json={'jsonrpc':'2.0','id':1,'method':'ping'},headers=HEADERS);await expect('unauthenticated',r.status_code==401)
        pr=(await browser.get(ISSUER+'/.well-known/oauth-protected-resource/mcp')).json();await expect('resource_metadata',pr['resource']==RESOURCE)
        md=(await browser.get(ISSUER+'/.well-known/oauth-authorization-server')).json();await expect('issuer_metadata',md['issuer']==ISSUER)
        reg=await browser.post(md['registration_endpoint'],json={'client_name':'Local qualification','redirect_uris':[REDIRECT],'token_endpoint_auth_method':'none'});reg.raise_for_status();cid=reg.json()['client_id']
        async def grant():
            v=secrets.token_urlsafe(48);c=base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip('=');state=secrets.token_hex(16)
            r=await browser.get(ISSUER+'/authorize',params={'response_type':'code','client_id':cid,'redirect_uri':REDIRECT,'scope':'lab:read','state':state,'code_challenge':c,'code_challenge_method':'S256','resource':RESOURCE});r.raise_for_status()
            import re
            handle=re.search(r'name="handle" value="([^"]+)"',r.text).group(1)
            r=await browser.post(ISSUER+'/authorize',data={'handle':handle,'decision':'approve'},headers={'Origin':ISSUER});assert r.status_code==302
            up=parse_qs(urlsplit(r.headers['location']).query)['state'][0]
            r=await browser.get(ISSUER+'/callback',params={'state':up,'code':'fixture-owner-code'});assert r.status_code==302
            q=parse_qs(urlsplit(r.headers['location']).query);assert q['state']==[state] and q['iss']==[ISSUER]
            r=await browser.post(md['token_endpoint'],data={'grant_type':'authorization_code','code':q['code'][0],'client_id':cid,'redirect_uri':REDIRECT,'code_verifier':v,'resource':RESOURCE});r.raise_for_status();return r.json()
        tokens=await grant();await expect('access_token',tokens['expires_in']<=900)
        for session in (1,2):
            auth={'Authorization':'Bearer '+tokens['access_token']}
            async with httpx2.AsyncClient(verify=tls,trust_env=False,follow_redirects=False,headers=auth,timeout=30) as http:
                async with Client(transport(RESOURCE,http_client=http)) as client:
                    assert client.server_info.version=='0.6.0';listed=await client.list_tools();assert {t.name for t in listed.tools}==set(fixtures())
                    for name,(args,expected) in fixtures().items():
                        t=time.perf_counter();r=await client.call_tool(name,args);assert not r.is_error and r.structured_content==expected,name
                        assert json.loads(r.content[0].text)==expected,name
                        bad=await client.call_tool(name,{});assert bad.is_error,name
                        rows.append({'session':session,'tool':name,'positive':'PASS','negative':'PASS','wall_ms':(time.perf_counter()-t)*1000})
                    async def parallel(name):
                        args,expected=fixtures()[name];r=await client.call_tool(name,args);assert not r.is_error and r.structured_content==expected
                    await asyncio.gather(*(parallel(n) for n in list(fixtures())[:4]));checks.append('parallel_4_session_'+str(session))
            r=await browser.post(RESOURCE,json={'jsonrpc':'2.0','id':9,'method':'ping'},headers={**auth,**HEADERS,'Origin':'https://untrusted.invalid'});await expect('origin_denial_'+str(session),r.status_code==403)
            if session==1:
                refresh=await browser.post(md['token_endpoint'],data={'grant_type':'refresh_token','client_id':cid,'refresh_token':tokens['refresh_token'],'resource':RESOURCE});refresh.raise_for_status();tokens=refresh.json();checks.append('refresh')
        r=await browser.post(md['revocation_endpoint'],data={'client_id':cid,'token':tokens['access_token'],'token_type_hint':'access_token'});await expect('revoke',r.status_code==200)
        r=await browser.post(RESOURCE,json={'jsonrpc':'2.0','id':1,'method':'ping'},headers={**HEADERS,'Authorization':'Bearer '+tokens['access_token']});await expect('revoked_denied',r.status_code==401)
        tokens=await grant();checks.append('reauthorization')
        # Direct core port exists only in this loopback multi-process qualification.
        async with httpx2.AsyncClient(trust_env=False,timeout=10) as direct:
            r=await direct.post('http://127.0.0.1:8791/rpc',json={'jsonrpc':'2.0','id':1,'method':'ping'},headers={'X-Lab-Scope':'lab:read','X-Lab-Subject':'fixture-owner','X-Lab-Internal':'forged'});await expect('direct_core_denied',r.status_code==403)
    Path('integrated-evidence.json').write_text(json.dumps({'status':'PASS','scope':'local service binding, synthetic identity','sdk':'2.3.0','rows':rows,'checks':checks},indent=2));print('integrated',len(rows),'positive + negative; checks',len(checks))
if __name__=='__main__':asyncio.run(main(sys.argv[1]))
