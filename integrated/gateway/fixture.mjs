// Local synthetic identity only. Do not deploy this entrypoint.
import {createLabOAuth} from '../../oauth_runtime/adapter.mjs';
import {resourceHandler,guardedOAuth} from './transport.mjs';
const issuer='https://127.0.0.1:8790';
export default guardedOAuth(createLabOAuth({issuer,ownerId:'fixture-owner',allowedRedirects:['https://client.example.invalid/callback'],enableDcr:true,identity:{
 async begin(_env,state,challenge){return 'https://identity.example.invalid/authorize?'+new URLSearchParams({state,challenge});},
 async finish(_env,code){return code==='fixture-owner-code'?'fixture-owner':null;}
},handleResource:resourceHandler(issuer)}));
