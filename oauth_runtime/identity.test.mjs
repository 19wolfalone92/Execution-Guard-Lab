import {test} from 'node:test';
import assert from 'node:assert/strict';
import {githubIdentity} from './github_identity.mjs';
const env={GITHUB_OAUTH_CLIENT_ID:'synthetic-id',GITHUB_OAUTH_CLIENT_SECRET:'synthetic-secret'};
const callback='https://lab.invalid/callback',challenge='a'.repeat(43),verifier='b'.repeat(64);
test('fixed GitHub authorization URL, PKCE, no requested scopes or secret',async()=>{
 const u=new URL(await githubIdentity.begin(env,'synthetic-state',challenge,callback));
 assert.equal(u.origin+u.pathname,'https://github.com/login/oauth/authorize');assert.equal(u.searchParams.get('scope'),'');assert.equal(u.searchParams.get('code_challenge_method'),'S256');assert.equal(u.searchParams.get('code_challenge'),challenge);assert.equal(u.searchParams.get('state'),'synthetic-state');assert.equal(u.searchParams.get('redirect_uri'),callback);assert.ok(!u.toString().includes(env.GITHUB_OAUTH_CLIENT_SECRET));
});
test('fixed identity calls, only numeric ID returned; reject redirects and unexpected scopes',async()=>{
 const previous=globalThis.fetch;let calls=[];let token={access_token:'synthetic-token',scope:'',token_type:'bearer'},profile={id:12345,login:'name',email:'not-retained@example.invalid'};
 globalThis.fetch=async(url,init)=>{calls.push({url,init});return init.method==='DELETE'?new Response(null,{status:204}):Response.json(url.endsWith('/access_token')?token:profile);};
 try{
  assert.equal(await githubIdentity.finish(env,'code',verifier,callback),'12345');assert.equal(calls.length,3);assert.equal(calls[2].url,'https://api.github.com/applications/synthetic-id/token');assert.equal(calls[2].init.method,'DELETE');assert.equal(calls[2].init.redirect,'error');assert.deepEqual(JSON.parse(calls[2].init.body),{access_token:'synthetic-token'});assert.equal(calls[0].url,'https://github.com/login/oauth/access_token');assert.equal(calls[0].init.body.get('code_verifier'),verifier);assert.equal(calls[0].init.redirect,'error');assert.equal(calls[1].url,'https://api.github.com/user');assert.equal(calls[1].init.redirect,'error');
  for(const bad of [{scope:'repo'},{scope:undefined},{token_type:'basic'},{access_token:''},{error:'invalid_grant'}]){calls=[];token={access_token:'synthetic-token',scope:'',token_type:'bearer',...bad};assert.equal(await githubIdentity.finish(env,'code',verifier,callback),null);assert.equal(calls.length,('scope' in bad)?2:1);assert.ok(!calls.some(c=>c.url==='https://api.github.com/user'));}
  token={access_token:'synthetic-token',scope:'',token_type:'bearer'};for(const id of ['12345',0,-1,Number.MAX_SAFE_INTEGER+1,null]){profile={id};assert.equal(await githubIdentity.finish(env,'code',verifier,callback),null);}
 }finally{globalThis.fetch=previous;}
});
test('missing config fails without any request',async()=>{await assert.rejects(githubIdentity.begin({},'state',challenge,callback));await assert.rejects(githubIdentity.finish({},'code',verifier,callback));});

test('no Lab identity grant after app token retirement failure; no retry',async()=>{
 const previous=globalThis.fetch;let calls=[];
 globalThis.fetch=async(url,init)=>{calls.push(url);return init.method==='DELETE'?new Response(null,{status:403}):Response.json(url.endsWith('/access_token')?{access_token:'synthetic-token',scope:'',token_type:'bearer'}:{id:12345});};
 try{assert.equal(await githubIdentity.finish(env,'code',verifier,callback),null);assert.equal(calls.length,3);}finally{globalThis.fetch=previous;}
});
