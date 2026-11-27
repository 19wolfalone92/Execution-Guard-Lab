const MAX=128*1024,OUT=1024*1024;
const allowed=new Set(['2025-03-26','2025-06-18','2025-11-25']);
const fail=(s)=>new Response(null,{status:s,headers:{'Cache-Control':'no-store'}});
async function bounded(body,max){if(!body)return new Uint8Array();const reader=body.getReader(),chunks=[];let n=0;try{for(;;){const {done,value}=await reader.read();if(done)break;n+=value.length;if(n>max){await reader.cancel();throw new RangeError();}chunks.push(value);}const result=new Uint8Array(n);let off=0;for(const c of chunks){result.set(c,off);off+=c.length;}return result;}finally{reader.releaseLock();}}
export function resourceHandler(issuer){
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
   // Do not copy client-controlled headers or tokens into the binding request.
   const response=await env.CORE.fetch('https://lab-core.internal/rpc',{method:'POST',headers:{'Content-Type':'application/json','X-Lab-Internal':env.INTERNAL_KEY,'X-Lab-Scope':'lab:read','X-Lab-Subject':ctx.auth.userId},body:raw,redirect:'manual'});
   if(![200,202,400,413].includes(response.status))return fail(503);
   const payload=await bounded(response.body,OUT);
   return new Response(response.status===202?null:payload,{status:response.status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
  }catch(e){return fail(e instanceof RangeError?413:503);}finally{active--;}
 };
}
