// Real upstream identity adapter; never requests repo, organization, or write scopes.
// This module is NOT deployed and requires a separately configured GitHub OAuth App.
const requireConfig=env=>{if(!env.GITHUB_OAUTH_CLIENT_ID||!env.GITHUB_OAUTH_CLIENT_SECRET)throw new Error('identity configuration missing');};
export const githubIdentity={
  async begin(env,state,challenge,redirectUri){
    requireConfig(env);
    const url=new URL('https://github.com/login/oauth/authorize');
    for(const [k,v] of Object.entries({client_id:env.GITHUB_OAUTH_CLIENT_ID,redirect_uri:redirectUri,state,code_challenge:challenge,code_challenge_method:'S256',allow_signup:'false',scope:''}))url.searchParams.set(k,v);
    return url.toString();
  },
  async finish(env,code,verifier,redirectUri){
    requireConfig(env);
    const res=await fetch('https://github.com/login/oauth/access_token',{method:'POST',redirect:'error',headers:{Accept:'application/json','Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({client_id:env.GITHUB_OAUTH_CLIENT_ID,client_secret:env.GITHUB_OAUTH_CLIENT_SECRET,code,code_verifier:verifier,redirect_uri:redirectUri})});
    if(!res.ok)return null;const token=await res.json();
    if(typeof token.access_token!=='string'||token.error||String(token.scope||'').trim()!=='')return null;
    const profile=await fetch('https://api.github.com/user',{redirect:'error',headers:{Authorization:'Bearer '+token.access_token,Accept:'application/vnd.github+json','User-Agent':'Execution-Guard-Lab'}});
    if(!profile.ok)return null;const data=await profile.json();
    // Do not store or forward the upstream access token.
    return Number.isSafeInteger(data.id)&&data.id>0?String(data.id):null;
  }
};
