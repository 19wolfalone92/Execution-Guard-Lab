// Candidate, intentionally has no deployment configuration or automatic deployment path.
import {createLabOAuth} from '../../oauth_runtime/adapter.mjs';
import {githubIdentity} from '../../oauth_runtime/github_identity.mjs';
import {resourceHandler,guardedOAuth} from './transport.mjs';
let app;
export default {fetch(request,env,ctx){
 if(env.RELEASE_APPROVED!=='true'||!env.CORE||!env.OAUTH_KV||!env.GITHUB_OAUTH_CLIENT_ID||!env.GITHUB_OAUTH_CLIENT_SECRET||!/^\d+$/.test(env.OWNER_ID||'')||typeof env.INTERNAL_KEY!=='string'||env.INTERNAL_KEY.length<32||env.INTERNAL_KEY.startsWith('synthetic-'))return new Response('HOLD',{status:503});
 const issuer=env.ISSUER;try{if(new URL(issuer).origin!==issuer||!issuer.startsWith('https://'))throw Error();}catch{return new Response('HOLD',{status:503});}
 app??=guardedOAuth(createLabOAuth({issuer,ownerId:env.OWNER_ID,allowedRedirects:['https://chatgpt.com/connector_platform_oauth_redirect'],enableDcr:true,identity:githubIdentity,handleResource:resourceHandler(issuer)}));
 return app.fetch(request,env,ctx);
}};
