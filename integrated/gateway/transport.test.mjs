import {test} from 'node:test';import assert from 'node:assert/strict';import {resourceHandler,guardedOAuth} from './transport.mjs';
const issuer='https://lab.invalid',headers={'Accept':'application/json, text/event-stream','Content-Type':'application/json'},key='synthetic-key-not-for-production-12345';
const ctx={auth:{userId:'owner'}};
function req(body='{}',extra={}){return new Request(issuer+'/mcp',{method:'POST',headers:{...headers,...extra},body});}
test('binding target fixed, caller credentials not forwarded, subject overwritten',async()=>{
 let count=0;const env={INTERNAL_KEY:key,CORE:{async fetch(url,init){count++;assert.equal(url,'https://lab-core.internal/rpc');assert.equal(init.headers['X-Lab-Subject'],'owner');assert.equal(init.headers['X-Lab-Internal'],key);assert.equal(init.headers.Authorization,undefined);return Response.json({jsonrpc:'2.0',id:1,result:{}});}}};
 const h=resourceHandler(issuer);const r=await h(req('{}',{'Authorization':'Bearer synthetic','X-Lab-Internal':'forged','X-Lab-Subject':'other'}),env,ctx);assert.equal(r.status,200);assert.equal(count,1);
 for(const [request,status] of [[req('{}',{Origin:'https://other.invalid'}),403],[req('{}',{'Mcp-Session-Id':'bad'}),404],[req('x'.repeat(128*1024+1)),413],[req('{}',{'MCP-Protocol-Version':'1900-01-01'}),400]])assert.equal((await h(request,env,ctx)).status,status);assert.equal(count,1);
});
test('output limit, missing binding and four-concurrent local gate',async()=>{
 const h=resourceHandler(issuer);assert.equal((await h(req(),{},ctx)).status,503);const env={INTERNAL_KEY:key,CORE:{async fetch(){return new Response('x'.repeat(1024*1024+1));}}};assert.equal((await h(req(),env,ctx)).status,413);
 let release;const blocker=new Promise(resolve=>release=resolve);env.CORE.fetch=async()=>{await blocker;return Response.json({});};const active=Array.from({length:4},()=>h(req(),env,ctx));assert.equal((await h(req(),env,ctx)).status,429);release();assert.deepEqual((await Promise.all(active)).map(r=>r.status),[200,200,200,200]);
});
test('OAuth guard rejects missing PKCE and oversized consent; passes bounded valid input',async()=>{
 let count=0;const app=guardedOAuth({async fetch(r){count++;return new Response(await r.text());}});assert.equal((await app.fetch(new Request(issuer+'/authorize'),{},{})).status,400);
 const r=await app.fetch(new Request(issuer+'/authorize',{method:'POST',body:'a'.repeat(8193)}),{},{});assert.equal(r.status,413);assert.equal(count,0);
 const ok=await app.fetch(new Request(issuer+'/authorize',{method:'POST',body:'handle=synthetic'}),{},{});assert.equal(await ok.text(),'handle=synthetic');assert.equal(count,1);
});
test('body deadline stops before binding call',async()=>{
 let count=0;const h=resourceHandler(issuer),env={INTERNAL_KEY:key,CORE:{async fetch(){count++;return Response.json({});}}};
 const body=new ReadableStream({start(){}});
 const request=new Request(issuer+'/mcp',{method:'POST',headers,body,duplex:'half'});
 assert.equal((await h(request,env,ctx)).status,408);assert.equal(count,0);
});
test('per-isolate fixed-window cap does not forward the 181st request',async()=>{
 let count=0;const h=resourceHandler(issuer),env={INTERNAL_KEY:key,CORE:{async fetch(){count++;return Response.json({});}}};
 for(let i=0;i<180;i++)assert.equal((await h(req(),env,ctx)).status,200);
 assert.equal((await h(req(),env,ctx)).status,429);assert.equal(count,180);
});
