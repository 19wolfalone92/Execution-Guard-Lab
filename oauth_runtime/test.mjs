import {createTestHarness} from 'wrangler';
import {createHash,randomBytes} from 'node:crypto';
import {writeFileSync} from 'node:fs';
const issuer='https://lab-qualification.invalid',resource=issuer+'/mcp',redirect='https://client.example.invalid/callback';
const harness=createTestHarness({workers:[{configPath:'./wrangler.jsonc'}]});
const worker=harness.getWorker('eglab-oauth-local-fixture-only');
const rows=[];let failed=0;
function check(name,condition){rows.push({name,status:condition?'PASS':'FAIL'});if(!condition)failed++;console.log(name,condition?'PASS':'FAIL');if(!condition)throw Error('assertion '+name);}
const fetch=(url,init={})=>worker.fetch(url,{...init,redirect:'manual'});
const post=(url,form,headers={})=>fetch(url,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded',...headers},body:new URLSearchParams(form)});
const cookies=r=>(r.headers.getSetCookie?.()||[r.headers.get('set-cookie')]).filter(Boolean).map(s=>s.split(';')[0]).join('; ');
async function start(client,scope='lab:read',uri=redirect){
 const verifier=randomBytes(48).toString('base64url'),challenge=createHash('sha256').update(verifier).digest('base64url');
 const url=new URL(issuer+'/authorize');for(const[k,v]of Object.entries({response_type:'code',client_id:client,redirect_uri:uri,scope,state:'client-state',code_challenge:challenge,code_challenge_method:'S256',resource}))url.searchParams.set(k,v);
 const res=await fetch(url);const html=await res.text();return {verifier,res,handle:/name="handle" value="([^"]+)"/.exec(html)?.[1],cookie:cookies(res)};
}
async function browser(client,{decision='approve',code='fixture-owner-code',missingCookie=false}={}){
 const s=await start(client);if(s.res.status!==200||!s.handle)throw Error('consent page missing');
 const r=await post(issuer+'/authorize',{handle:s.handle,decision},{Origin:issuer,...(missingCookie?{}:{Cookie:s.cookie})});
 if(decision==='deny'||missingCookie||r.status!==302)return {...s,response:r};
 const loc=new URL(r.headers.get('Location'));const callback=issuer+'/callback?'+new URLSearchParams({state:loc.searchParams.get('state'),code});
 const response=await fetch(callback,{headers:{Cookie:cookies(r)}});return {...s,response};
}
async function exchange(client,b,verifier=b.verifier,res=resource){
 const c=new URL(b.response.headers.get('Location')).searchParams.get('code');return post(issuer+'/oauth/token',{grant_type:'authorization_code',client_id:client,code:c,redirect_uri:redirect,code_verifier:verifier,resource:res});
}
async function main(){
 await harness.listen();
 const unauth=await fetch(resource);check('missing_token_401',unauth.status===401);check('discovery_challenge',unauth.headers.get('www-authenticate')?.includes('resource_metadata='));
 const pr=await (await fetch(issuer+'/.well-known/oauth-protected-resource/mcp')).json();check('protected_resource_metadata',pr.resource===resource&&pr.authorization_servers?.includes(issuer));
 const as=await (await fetch(issuer+'/.well-known/oauth-authorization-server')).json();check('issuer_pkce_metadata',as.issuer===issuer&&as.code_challenge_methods_supported?.includes('S256'));
 const registration=await fetch(as.registration_endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({client_name:'Synthetic qualification client',redirect_uris:[redirect],token_endpoint_auth_method:'none'})});const c=await registration.json();check('registration',registration.status>=200&&registration.status<300&&typeof c.client_id==='string');const client=c.client_id;
 const invalidRedirect=await start(client,'lab:read','https://other.invalid/callback');check('wrong_redirect_rejected',invalidRedirect.res.status!==200&&!invalidRedirect.res.headers.get('Location')?.includes('code='));
 const noConsent=await browser(client,{missingCookie:true});check('missing_consent_cookie_rejected',noConsent.response.status!==302||!noConsent.response.headers.get('Location')?.startsWith('https://identity.example.invalid/'));
 const denied=await browser(client,{decision:'deny'});check('owner_denial',denied.response.status===302&&new URL(denied.response.headers.get('Location')).searchParams.get('error')==='access_denied');
 const other=await browser(client,{code:'fixture-other-code'});check('unknown_owner_rejected',other.response.status===302&&new URL(other.response.headers.get('Location')).searchParams.get('error')==='access_denied');
 const b=await browser(client);const cb=new URL(b.response.headers.get('Location'));check('consent_and_owner_code',b.response.status===302&&!!cb.searchParams.get('code')&&cb.searchParams.get('state')==='client-state'&&cb.searchParams.get('iss')===issuer);
 const bad=await exchange(client,b,'wrong-verifier');check('wrong_pkce_rejected',bad.status>=400);
 const good=await browser(client);const wrongAud=await exchange(client,good,good.verifier,'https://other.invalid/mcp');check('wrong_resource_rejected',wrongAud.status>=400);
 const tokenResponse=await exchange(client,good);const tokens=await tokenResponse.json();check('correct_pkce_access_token',tokenResponse.status===200&&typeof tokens.access_token==='string'&&tokens.expires_in<=900&&typeof tokens.refresh_token==='string');
 const replay=await exchange(client,good);check('code_replay_rejected',replay.status>=400);
 const auth={Authorization:'Bearer '+tokens.access_token};const access=await fetch(resource,{headers:auth});check('authorized_fixture_resource',access.status===200&&(await access.json()).qualified===true);
 const forged=await fetch(resource,{headers:{Authorization:'Bearer forged-token'}});check('forged_token_rejected',forged.status===401);
 const refreshed=await post(as.token_endpoint,{grant_type:'refresh_token',client_id:client,refresh_token:tokens.refresh_token,resource});const rotated=await refreshed.json();check('refresh',refreshed.status===200&&typeof rotated.access_token==='string'&&rotated.access_token!==tokens.access_token);
 const access2=await fetch(resource,{headers:{Authorization:'Bearer '+rotated.access_token}});check('refreshed_token_access',access2.status===200);
 const revoke=await post(as.revocation_endpoint,{client_id:client,token:rotated.access_token,token_type_hint:'access_token'});check('revocation_request',revoke.status===200);
 const after=await fetch(resource,{headers:{Authorization:'Bearer '+rotated.access_token}});check('revoked_token_rejected',after.status===401);
}
try{await main();}catch(e){if(!failed)rows.push({name:'harness_runtime',status:'FAIL',error:String(e?.message||e).slice(0,200)});failed++;}finally{await harness.close();writeFileSync('../oauth-local-evidence.json',JSON.stringify({scope:'official OAuth provider; local synthetic identity; no real user, no MCP tool calls',passed:rows.filter(r=>r.status==='PASS').length,failed,rows},null,2)+'\n');}
process.exitCode=failed?1:0;
