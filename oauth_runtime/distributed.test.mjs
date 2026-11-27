// Real workerd multi-Worker test; all hosts and identifiers are synthetic.
// This does not model Cloudflare edge locations or cross-region KV propagation.
import {Miniflare} from 'miniflare';
import {readFile,mkdtemp,rm,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';import {join} from 'node:path';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
const dir=await mkdtemp(join(tmpdir(),'eglab-admission-'));
const admission=await readFile(new URL('../integrated/gateway/admission.mjs',import.meta.url),'utf8');
const binding={ADMISSION:{className:'Admission',scriptName:'admission-host',useSQLite:true}};
const client=`export default {async fetch(request,env){const u=new URL(request.url);if(request.method!=='POST'||!['/acquire','/release'].includes(u.pathname))return new Response(null,{status:404});const name=request.headers.get('X-Test-Object');if(!['race','rate'].includes(name))return new Response(null,{status:400});const stub=env.ADMISSION.get(env.ADMISSION.idFromName(name));return stub.fetch('https://admission.internal'+u.pathname,{method:'POST',headers:{'X-Lab-Lease':request.headers.get('X-Lab-Lease'),'X-Lab-Client':request.headers.get('X-Lab-Client')}});}};`;
const options={host:'127.0.0.1',port:0,cf:false,enableDevRegistry:false,resourcePersistencePath:dir,workers:[
 {name:'admission-host',modules:true,compatibilityDate:'2026-11-26',script:admission+'\nexport default {fetch(){return new Response(null,{status:404});}};',durableObjects:{ADMISSION:{className:'Admission',useSQLite:true}}},
 ...['gateway-a','gateway-b'].map(name=>({name,modules:true,compatibilityDate:'2026-11-26',script:client,durableObjects:binding}))]};
let mf=new Miniflare(options);const checks=[];const record=(name,value)=>{assert(value,name);checks.push(name);};
let gateways;
async function initialize(){await mf.ready;gateways=await Promise.all(['gateway-a','gateway-b'].map(n=>mf.getWorker(n)));}
const A='a'.repeat(64),B='b'.repeat(64);const lease=(client=A)=>({client,id:randomUUID()});
async function req(g,op,l,object='race'){return (await gateways[g].fetch('https://fixture.invalid/'+op,{method:'POST',headers:{'X-Test-Object':object,'X-Lab-Client':l.client,'X-Lab-Lease':l.id}})).status;}
try{
 await initialize();
 const slots=Array.from({length:12},(_,i)=>({g:i%2,l:lease(i%2?A:B)}));const result=await Promise.all(slots.map(async s=>({...s,status:await req(s.g,'acquire',s.l)})));
 const accepted=result.filter(x=>x.status===204);record('race_four_global',accepted.length===4&&result.filter(x=>x.status===429).length===8);
 record('both_workers_share_capacity',await req(0,'acquire',lease())===429&&await req(1,'acquire',lease())===429);
 const one=accepted.pop();record('wrong_client_cannot_release',await req(1-one.g,'release',{...one.l,client:one.l.client===A?B:A})===409);
 record('cross_worker_release',await req(1-one.g,'release',one.l)===204);record('duplicate_release_rejected',await req(one.g,'release',one.l)===409);
 const newLease=lease();record('capacity_recovered_after_completion',await req(0,'acquire',newLease)===204);
 // Recreate workerd with the same SQLite persistence. No release on unknown completion.
 await mf.dispose();mf=new Miniflare(options);await initialize();
 record('persisted_slots_survive_restart',await req(1,'acquire',lease())===429);
 for(const a of [...accepted,{g:0,l:newLease}])assert.equal(await req(1-a.g,'release',a.l),204);
 record('all_slots_released',await req(1,'acquire',lease())===204);
 const start=Date.now();
 for(let i=0;i<180;i++){const l=lease(i<160?A:B);assert.equal(await req(i%2,'acquire',l,'rate'),204);assert.equal(await req(1-i%2,'release',l,'rate'),204);if(i===159)record('client_limit_shared',await req(1,'acquire',lease(A),'rate')===429);}
 record('global_limit_shared',await req(0,'acquire',lease(B),'rate')===429);record('rate_test_within_window',Date.now()-start<60000);
 const out={scope:'local workerd, separate Worker instances, same SQLite Durable Object; synthetic clients, no OAuth or cloud locations',checks,passed:checks.length,status:'PASS'};
 await writeFile('../distributed-evidence.json',JSON.stringify(out,null,2));console.log(JSON.stringify(out));
}finally{await mf.dispose();await rm(dir,{recursive:true,force:true});}
