import {acquire} from './admission.mjs';
const MAX=128*1024,OUT=1024*1024;
const allowed=new Set(['2025-03-26','2025-06-18','2025-11-25']);
const fail=(s)=>new Response(null,{status:s,headers:{'Cache-Control':'no-store',...(s===429?{'Retry-After':'60'}:{})}});
class ReadDeadline extends Error {}
async function bounded(body,max,timeoutMs=5000){
 if(!body)return new Uint8Array();const reader=body.getReader(),chunks=[];let n=0,timer;
 const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>reject(new ReadDeadline()),timeoutMs);});
 try{
  for(;;){const {done,value}=await Promise.race([reader.read(),deadline]);if(done)break;n+=value.length;if(n>max)throw new RangeError();chunks.push(value);}
  const result=new Uint8Array(n);let off=0;for(const c of chunks){result.set(c,off);off+=c.length;}return result;
 }catch(e){void reader.cancel().catch(()=>{});throw e;}finally{clearTimeout(timer);reader.releaseLock();}
}
// All OAuth POST bodies are bounded before the official library reads them.
// Force S256 even for confidential clients, not just public registrations.
export function guardedOAuth(app){return {async fetch(request,env,ctx){
 const u=new URL(request.url);
 if(u.pathname==='/authorize'&&request.method==='GET'){
  if(u.searchParams.getAll('code_challenge').length!==1||u.searchParams.getAll('code_challenge_method').length!==1||!/^[-_A-Za-z0-9]{43}$/.test(u.searchParams.get('code_challenge')||'')||u.searchParams.get('code_challenge_method')!=='S256')return fail(400);
 }
 if(request.method==='POST'&&u.pathname!=='/mcp'){
  try{const data=await bounded(request.body,u.pathname==='/authorize'?8192:MAX);request=new Request(request,{body:data});}
  catch(e){return fail(e instanceof RangeError?413:e instanceof ReadDeadline?408:400);}
 }
 return app.fetch(request,env,ctx);
}};}
export function resourceHandler(issuer,{distributed=false}={}){
 let active=0,windowStart=0,count=0;
 return async (request,env,ctx)=>{
  const u=new URL(request.url);if(u.pathname!=='/mcp'||u.search)return fail(404);
  const origin=request.headers.get('Origin');if(origin&&origin!==issuer)return fail(403);
  if(request.headers.has('Mcp-Session-Id'))return fail(404);
  if(request.method!=='POST')return fail(405);
  if(request.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase()!=='application/json')return fail(415);
  const accept=request.headers.get('Accept')||'';if(!accept.includes('application/json')||!accept.includes('text/event-stream'))return fail(406);
  const protocol=request.headers.get('MCP-Protocol-Version');if(protocol&&!allowed.has(protocol))return fail(400);
  if(!env.CORE||typeof env.INTERNAL_KEY!=='string'||env.INTERNAL_KEY.length<32)return fail(503);
  const now=Date.now();if(now-windowStart>=60000){windowStart=now;count=0;}if(count>=180||active>=4)return fail(429);count++;active++;
  try{
   const raw=await bounded(request.body,MAX);
   const slot=distributed?await acquire(env,ctx.auth):null;
   if(slot&&slot.status!==204)return fail(slot.status);
   // Do not copy client-controlled headers or tokens into the binding request.
   const response=await env.CORE.fetch('https://lab-core.internal/rpc',{method:'POST',headers:{'Content-Type':'application/json','X-Lab-Internal':env.INTERNAL_KEY,'X-Lab-Scope':'lab:read','X-Lab-Subject':ctx.auth.userId},body:raw,redirect:'manual'});
   // A returned, fully consumed response proves the computation has ended.
   // On ambiguous transport failure do not release the durable slot.
   const payload=await bounded(response.body,OUT);
   if(slot&&!await slot.release())return fail(503);
   if(![200,202,400,413].includes(response.status))return fail(503);
   return new Response(response.status===202?null:payload,{status:response.status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
  }catch(e){return fail(e instanceof RangeError?413:e instanceof ReadDeadline?408:503);}finally{active--;}
 };
}
