"""Loopback-only experimental Streamable HTTP (MCP 2025-11-25 handshake).
Not an authenticated production service. No public bind option. No request-body logs.
"""
import argparse, json, socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from lab import MAX_LINE, decode, rpc

VERSIONS={'2025-03-26','2025-06-18','2025-11-25'}
class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    server_version='ExecutionGuardLab/0.2.0'
    sys_version=''
    def setup(self):
        super().setup();self.connection.settimeout(3)
    def log_message(self,*args):pass
    def reply(self,status,body=None,allow=None):
        data=b'' if body is None else json.dumps(body,allow_nan=False,ensure_ascii=True).encode()
        self.send_response(status);self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)))
        if body is not None:self.send_header('Content-Type','application/json')
        if allow:self.send_header('Allow',allow)
        self.send_header('Connection','close');self.end_headers();self.close_connection=True
        if data:self.wfile.write(data)
    def gate(self):
        port=self.server.server_port;allowed={f'127.0.0.1:{port}',f'localhost:{port}'}
        if self.headers.get('Host') not in allowed:return self.reply(403),False
        origin=self.headers.get('Origin')
        if origin is not None and origin not in {'http://'+h for h in allowed}:return self.reply(403),False
        if self.path!='/mcp':return self.reply(404),False
        version=self.headers.get('MCP-Protocol-Version')
        if version is not None and version not in VERSIONS:return self.reply(400),False
        return None,True
    def do_GET(self):
        if self.gate()[1]:self.reply(405,allow='POST')
    do_DELETE=do_GET
    do_OPTIONS=do_GET
    def do_POST(self):
        if not self.gate()[1]:return
        if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))!=1:return self.reply(400)
        length=self.headers.get('Content-Length','')
        if not length.isascii() or not length.isdigit() or len(length)>8:return self.reply(400)
        size=int(length)
        if size>MAX_LINE:return self.reply(413)
        if self.headers.get_content_type()!='application/json':return self.reply(415)
        accept={a.split(';')[0].strip().lower() for a in self.headers.get('Accept','').split(',')}
        if not {'application/json','text/event-stream'}<=accept:return self.reply(406)
        try:raw=self.rfile.read(size)
        except (TimeoutError,OSError):return self.reply(408)
        if len(raw)!=size:return self.reply(400)
        try:request=decode(raw)
        except (ValueError,RecursionError):return self.reply(400,{'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'invalid_json'}})
        response=rpc(request)
        self.reply(202 if response is None else 200,response)

def serve(port=8765):
    with HTTPServer(('127.0.0.1',port),Handler) as server:
        print(json.dumps({'listen':'127.0.0.1','port':server.server_port,'path':'/mcp','version':'0.2.0'}),flush=True)
        server.serve_forever()
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);serve(parser.parse_args().port)
