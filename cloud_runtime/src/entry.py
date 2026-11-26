"""LOCAL-ONLY runtime probe: fixed synthetic cases, no user input or credentials."""
from workers import WorkerEntrypoint, Response
from urllib.parse import urlsplit
from lab import rpc
from fixed_cases import CASES

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = urlsplit(request.url).path
        if request.method != 'GET': return Response('method not allowed', status=405)
        if path == '/health': return Response('qualification-only')
        if not path.startswith('/case/'): return Response('not found', status=404)
        part = path[6:]
        if not part.isascii() or not part.isdecimal() or len(part)>3: return Response('not found',status=404)
        index=int(part)
        if index>=len(CASES): return Response('not found', status=404)
        c=CASES[index]
        result=rpc({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':c['name'],'arguments':c['arguments']}})['result']
        return Response.json({'result':result})
