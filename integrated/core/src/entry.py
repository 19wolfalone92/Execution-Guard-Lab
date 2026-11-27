"""Closed Worker transport. No routing, network egress or tool execution beyond lab.rpc."""
import hmac, json
from urllib.parse import urlsplit
from workers import WorkerEntrypoint, Response
from lab import decode, rpc, MAX_LINE

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        if urlsplit(request.url).path != '/rpc' or request.method != 'POST':
            return Response('Not found',status=404)
        expected=getattr(self.env,'INTERNAL_KEY',None)
        actual=request.headers.get('X-Lab-Internal') or ''
        if not isinstance(expected,str) or len(expected)<32 or not hmac.compare_digest(actual.encode(),expected.encode()):
            return Response('Forbidden',status=403)
        if request.headers.get('X-Lab-Scope')!='lab:read' or not request.headers.get('X-Lab-Subject'):
            return Response('Forbidden',status=403)
        try:
            raw=await request.bytes()
            if len(raw)>MAX_LINE:return Response('Request too large',status=413)
            result=rpc(decode(bytes(raw)))
            if result is None:return Response('',status=202)
            if isinstance(result,dict) and 'result' in result and 'serverInfo' in result['result']:
                result['result']['serverInfo']['version']='0.6.0'
            payload=json.dumps(result,ensure_ascii=True,allow_nan=False)
            if len(payload)>1024*1024:return Response('Response too large',status=413)
            return Response(payload,headers={'Content-Type':'application/json','Cache-Control':'no-store'})
        except (ValueError,TypeError,UnicodeError,RecursionError):
            return Response('{"jsonrpc":"2.0","id":null,"error":{"code":-32700,"message":"invalid_json"}}',headers={'Content-Type':'application/json'},status=400)
