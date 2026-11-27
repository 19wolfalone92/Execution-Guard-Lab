// Real upstream identity adapter; never requests repo, organization, or write scopes.
// This module is NOT deployed and requires a separately configured GitHub OAuth App.
const requireConfig=env=>{if(!/^[A-Za-z0-9._-]{1,256}$/.test(env.GITHUB_OAUTH_CLIENT_ID||'')||!/^[-_A-Za-z0-9.]{1,512}$/.test(env.GITHUB_OAUTH_CLIENT_SECRET||''))throw new Error('identity configuration missing');};
const deadline=()=>AbortSignal.timeout(10000);
async function retire(env,token){
  try{const r=await fetch('https://api.github.com/applications/'+encodeURIComponent(env.GITHUB_OAUTH_CLIENT_ID)+'/token',{method:'DELETE',redirect:'error',signal:deadline(),headers:{Authorization:'Basic '+btoa(env.GITHUB_OAUTH_CLIENT_ID+':'+env.GITHUB_OAUTH_CLIENT_SECRET),Accept:'application/vnd.github+json','Content-Type':'application/json','User-Agent':'Execution-Guard-Lab'},body:JSON.stringify({access_token:token})});return r.status===204;}catch{return false;}
}
export const githubIdentity={
  async begin(env,state,challenge,redirectUri){
    requireConfig(env);
    const url=new URL('https://github.com/login/oauth/authorize');
    for(const [k,v] of Object.entries({client_id:env.GITHUB_OAUTH_CLIENT_ID,redirect_uri:redirectUri,state,code_challenge:challenge,code_challenge_method:'S256',allow_signup:'false',scope:''}))url.searchParams.set(k,v);
    return url.toString();
  },
  async finish(env,code,verifier,redirectUri){
    requireConfig(env);
    const res=await fetch('https://github.com/login/oauth/access_token',{method:'POST',redirect:'error',signal:deadline(),headers:{Accept:'application/json','Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({client_id:env.GITHUB_OAUTH_CLIENT_ID,client_secret:env.GITHUB_OAUTH_CLIENT_SECRET,code,code_verifier:verifier,redirect_uri:redirectUri})});
    if(!res.ok)return null;const token=await res.json();
    if(typeof token.access_token!=='string'||!token.access_token||token.access_token.length>4096||token.error||String(token.token_type||'').toLowerCase()!=='bearer')return null;
    let userId=null;
    try{
      // Even if GitHub returns unexpected scopes, retire this app's newly issued token;
      // never use it to read profile or any repository data.
      if(token.scope===''){
        const profile=await fetch('https://api.github.com/user',{redirect:'error',signal:deadline(),headers:{Authorization:'Bearer '+token.access_token,Accept:'application/vnd.github+json','User-Agent':'Execution-Guard-Lab'}});
        if(profile.ok){const data=await profile.json();if(Number.isSafeInteger(data.id)&&data.id>0)userId=String(data.id);}
      }
    }catch{userId=null;}
    // This is the dedicated Lab identity app's token, not a GitHub connector
    // credential. Grant only after confirmed retirement; no retry on denial.
    return await retire(env,token.access_token)?userId:null;
  }
};
