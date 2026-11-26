// LOCAL-ONLY synthetic identity. No credentials, real accounts, MCP tools or deploy workflow.
import {createLabOAuth} from './adapter.mjs';
export default createLabOAuth({issuer:'https://lab-qualification.invalid',ownerId:'fixture-owner',allowedRedirects:['https://client.example.invalid/callback'],enableDcr:true,identity:{
  async begin(_env,state,challenge){return 'https://identity.example.invalid/authorize?'+new URLSearchParams({state,challenge});},
  async finish(_env,code){return code==='fixture-owner-code'?'fixture-owner':'fixture-other';}
},handleResource(){return Response.json({qualified:true});}});
