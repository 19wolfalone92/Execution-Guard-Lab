// Single private Durable Object per Lab. Durable transactions serialize admission.
// A lost completion deliberately strands its slot: no time-based lease expiry can
// permit a fifth still-running computation. Recovery requires proven drain.
const WINDOW=60000, GLOBAL=180, CLIENT=160, CONCURRENT=4;
const idPattern=/^[0-9a-f]{64}$/;
const leasePattern=/^[0-9a-f-]{36}$/;
const response=(status)=>new Response(null,{status,headers:{'Cache-Control':'no-store',...(status===429?{'Retry-After':'60'}:{})}});
export class Admission {
 constructor(ctx){this.storage=ctx.storage;}
 async fetch(request){
  const u=new URL(request.url);if(request.method!=='POST'||u.origin!=='https://admission.internal'||u.search)return response(404);
  const lease=request.headers.get('X-Lab-Lease')||'',client=request.headers.get('X-Lab-Client')||'';
  if(!leasePattern.test(lease)||!idPattern.test(client))return response(400);
  try {
   const status=await this.storage.transaction(async tx=>{
    const s=await tx.get('admission-v1')??{last:0,hits:[],active:[]};
    const now=Date.now();if(now<s.last)return 503;
    if(u.pathname==='/release'){
     const n=s.active.findIndex(x=>x.lease===lease&&x.client===client);if(n<0)return 409;
     s.active.splice(n,1);s.last=now;await tx.put('admission-v1',s);return 204;
    }
    if(u.pathname!=='/acquire')return 404;
    s.hits=s.hits.filter(x=>x.at>now-WINDOW);
    if(s.active.some(x=>x.lease===lease))return 409;
    if(s.active.length>=CONCURRENT||s.hits.length>=GLOBAL||s.hits.filter(x=>x.client===client).length>=CLIENT)return 429;
    s.hits.push({at:now,client});s.active.push({lease,client});s.last=now;
    await tx.put('admission-v1',s);return 204;
   });return response(status);
  }catch{return response(503);}
 }
}
export async function acquire(env,auth){
 if(!env.ADMISSION||typeof auth?.clientId!=='string'||!auth.clientId||auth.clientId.length>2048||auth.userId!==env.OWNER_ID||!auth.scope?.includes('lab:read'))return {status:503};
 try{
  const bytes=new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(auth.clientId)));
  const client=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join(''),lease=crypto.randomUUID();
  const stub=env.ADMISSION.get(env.ADMISSION.idFromName('lab-global-v1'));
  const headers={'X-Lab-Lease':lease,'X-Lab-Client':client};
  const r=await stub.fetch('https://admission.internal/acquire',{method:'POST',headers});
  if(r.status!==204)return {status:r.status===429?429:503};
  return {status:204,release:async()=>{try{return (await stub.fetch('https://admission.internal/release',{method:'POST',headers})).status===204;}catch{return false;}}};
 }catch{return {status:503};}
}
