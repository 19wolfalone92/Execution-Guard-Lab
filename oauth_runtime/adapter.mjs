// Candidate integration with the official provider. No deployment configuration.
import { OAuthAuthorizationServer, OAuthResourceServer, AuthorizationError, authorizationErrorRedirect, insufficientScope } from '@cloudflare/workers-oauth-provider';
const SCOPE='lab:read';
const escapeHtml=s=>String(s).replace(/[&<>"']/g,c=>`&#${c.charCodeAt(0)};`);
const fail=(status=400)=>new Response('Authorization not completed',{status,headers:{'Cache-Control':'no-store','Content-Type':'text/plain; charset=utf-8'}});
export async function s256(verifier){
  const bytes=new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier)));
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
export function createLabOAuth({issuer,ownerId,identity,handleResource,enableDcr=false,allowedRedirects,enableCimd=false}){
  const resource=issuer+'/mcp';
  if(!issuer.startsWith('https://')||!ownerId||!allowedRedirects?.length) throw new Error('incomplete oauth configuration');
  const server=new OAuthAuthorizationServer({issuer,resources:[resource],scopesSupported:[SCOPE],accessTokenTTL:900,refreshTokenTTL:7*86400,clientIdMetadataDocumentEnabled:enableCimd,...(enableDcr?{clientRegistrationEndpoint:'/oauth/register'}:{})});
  const protectedResource=new OAuthResourceServer({resourceMetadata:{resource,authorization_servers:[issuer],resource_name:'Execution Guard Lab'},requiredScopes:[SCOPE],validateToken:env=>(aud,token)=>server.validateToken(aud,token,env),handler:{fetch(request,env,ctx){
    if(ctx.auth.userId!==ownerId||ctx.props?.userId!==ownerId)return fail(403);
    if(!ctx.auth.scope.includes(SCOPE))return insufficientScope(ctx.auth,[SCOPE]);
    if(ctx.auth.audience!==resource)return fail(401);
    return handleResource(request,env,ctx);
  }}});
  function validRequest(req){return allowedRedirects.includes(req.redirectUri)&&req.scope.length===1&&req.scope[0]===SCOPE;}
  async function authorize(request,env){
    const oauth=server.getOAuthApi(env);const url=new URL(request.url);
    if(request.method==='GET'){
      const req=await oauth.parseAuthRequest(request);
      if(!validRequest(req))return fail();
      const details=await oauth.describeConsent(req), consent=await oauth.beginConsent(req);
      consent.headers.set('Content-Type','text/html; charset=utf-8');
      consent.headers.set('Cache-Control','no-store');
      return new Response(`<!doctype html><meta charset="utf-8"><title>Lab authorization</title><h1>Authorize ${escapeHtml(details.clientName)}</h1><p>Publisher: ${escapeHtml(details.clientDomain||'self-registered client')}</p><p>Redirect host: ${escapeHtml(details.redirectHost)}</p>${details.redirectIsLoopback?'<p>Local application: verify that you initiated this request.</p>':''}<p>Scope: lab:read (computation and diagnostics only)</p><form method="post"><input type="hidden" name="handle" value="${escapeHtml(consent.handle)}"><button name="decision" value="approve">Allow</button><button name="decision" value="deny">Deny</button></form>`,{headers:consent.headers});
    }
    if(request.method!=='POST'||!request.headers.get('Content-Type')?.startsWith('application/x-www-form-urlencoded'))return fail(405);
    if(request.headers.get('Origin')!==issuer)return fail(403);
    const text=await request.text();if(text.length>8192)return fail(413);
    const form=new URLSearchParams(text),handle=form.get('handle')||'';
    if(form.get('decision')!=='approve'){
      const denied=await oauth.denyConsent(request,handle);return new Response(null,{status:302,headers:denied.headers});
    }
    const approved=await oauth.approveConsent(request,handle,{scope:[SCOPE]});
    if(!validRequest(approved.request))return fail();
    const verifier=crypto.randomUUID()+crypto.randomUUID();
    const upstream=await oauth.beginUpstream(approved.request,{data:{verifier},headers:approved.headers});
    upstream.headers.set('Location',await identity.begin(env,upstream.state,await s256(verifier),issuer+'/callback'));
    return new Response(null,{status:302,headers:upstream.headers});
  }
  async function callback(request,env){
    if(request.method!=='GET')return fail(405);
    const oauth=server.getOAuthApi(env),url=new URL(request.url);
    const {request:original,data,headers}=await oauth.finishUpstream(request);
    if(!validRequest(original))return fail();
    const deny=()=>{headers.set('Location',authorizationErrorRedirect(original,'access_denied'));return new Response(null,{status:302,headers});};
    if(url.searchParams.has('error')||!url.searchParams.get('code'))return deny();
    const userId=await identity.finish(env,url.searchParams.get('code'),data.verifier,issuer+'/callback');
    if(userId!==ownerId)return deny();
    const {redirectTo}=await oauth.completeAuthorization({request:original,userId,metadata:{},scope:[SCOPE],props:{userId}});
    headers.set('Location',redirectTo);return new Response(null,{status:302,headers});
  }
  return {async fetch(request,env,ctx){
    try{
      const u=new URL(request.url);if(u.origin!==issuer)return fail(400);
      if(u.pathname==='/authorize')return await authorize(request,env);
      if(u.pathname==='/callback')return await callback(request,env);
      if(u.pathname==='/mcp'||u.pathname==='/.well-known/oauth-protected-resource/mcp'||u.pathname==='/.well-known/oauth-protected-resource')return protectedResource.fetch(request,env,ctx);
      return server.fetch(request,env,ctx);
    }catch(error){
      if(error instanceof AuthorizationError && error.redirectTo){
        const target=new URL(error.redirectTo);if(allowedRedirects.some(x=>{const a=new URL(x);return a.origin===target.origin&&a.pathname===target.pathname;}))return Response.redirect(error.redirectTo,302);
      }
      return fail(error instanceof AuthorizationError?400:503);
    }
  }};
}
