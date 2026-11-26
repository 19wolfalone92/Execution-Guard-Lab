"""Independent official Python MCP SDK v1 qualification; no token logging.
Run from an authorized client host against the verified TLS endpoint.
Only sends the bundled synthetic fixtures. Requires the official SDK 1.30.0.
"""
import argparse
import asyncio
import getpass
import importlib.metadata
import json
from pathlib import Path
import ssl
import sys
from urllib.parse import urlsplit

HERE=Path(__file__).parent

def cases():
    report=json.loads((HERE/'BASELINE_RERUN_RPC.json').read_text(encoding='utf-8'))
    seen={}
    for row in report['stdio']:
        m=row['request'];r=row['response']
        if m['method']=='tools/call' and not r['result']['isError']:
            seen[m['params']['name']]=(m['params']['arguments'],r['result']['structuredContent'])
    if len(seen)!=23:raise RuntimeError('invalid_fixture_inventory')
    return seen

async def qualify(url,token,ca,output):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    import httpx
    fixtures=cases(); evidence=[]; requests=[]
    async def on_request(request):
        # Only locally generated MCP fixture JSON. Never record headers or URLs containing tokens.
        try:body=json.loads(request.content)
        except (ValueError,httpx.RequestNotRead):body=None
        requests.append({'method':request.method,'body':body})
    async def on_response(response):
        await response.aread()
        try:body=response.json()
        except ValueError:body=None
        requests.append({'status':response.status_code,'body':body})
    tls=ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()
    async with httpx.AsyncClient(verify=tls,headers={'Authorization':'Bearer '+token},trust_env=False,follow_redirects=False,timeout=15,event_hooks={'request':[on_request],'response':[on_response]}) as client:
        for repeat in (1,2):
            async with asyncio.timeout(90):
                async with streamable_http_client(url,http_client=client) as (read,write,_):
                    async with ClientSession(read,write) as session:
                        i=await session.initialize();assert i.serverInfo.version=='0.3.0'
                        assert i.protocolVersion in ('2025-03-26','2025-06-18','2025-11-25')
                        await session.send_ping()
                        tools=await session.list_tools();assert {t.name for t in tools.tools}==set(fixtures)
                        evidence.append({'repeat':repeat,'initialize':i.model_dump(mode='json',by_alias=True),'tools_count':len(tools.tools)})
                        for name,(args,expected) in fixtures.items():
                            result=await session.call_tool(name,arguments=args)
                            assert not result.isError and result.structuredContent==expected,name
                            assert json.loads(result.content[0].text)==expected,name
                            evidence.append({'repeat':repeat,'name':name,'state':'PASS','result':result.structuredContent})
                            bad=await session.call_tool(name,arguments={});assert bad.isError,name
                            evidence.append({'repeat':repeat,'name':name,'negative':'PASS'})
                        try:
                            unknown=await session.call_tool('nonexistent_lab_tool',arguments={});assert unknown.isError
                        except Exception as e:
                            from mcp.shared.exceptions import McpError
                            if not isinstance(e,McpError):raise
                            # Some official clients reject unknown tool names before the wire call.
                            evidence.append({'repeat':repeat,'unknown':'SDK-rejected (see wire log)'})
                        async def repeated(name):
                            args,expected=fixtures[name];r=await session.call_tool(name,arguments=args)
                            assert not r.isError and r.structuredContent==expected
                        await asyncio.gather(*(repeated(n) for n in list(fixtures)[:4]))
                        evidence.append({'repeat':repeat,'parallel':4,'state':'PASS'})
    Path(output).write_text(json.dumps({'sdk_version':importlib.metadata.version('mcp'),'scope':'authorized SDK client synthetic fixtures; not ChatGPT calls','results':evidence,'wire':requests},ensure_ascii=False,indent=2),encoding='utf-8')


def main():
    p=argparse.ArgumentParser();p.add_argument('--url');p.add_argument('--ca');p.add_argument('--output',default='SDK_EVIDENCE.json');p.add_argument('--check-install',action='store_true');a=p.parse_args()
    try:
        version=importlib.metadata.version('mcp')
        if version!='1.30.0':raise RuntimeError('expected official mcp==1.30.0')
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except (ImportError,importlib.metadata.PackageNotFoundError,RuntimeError) as e:
        print('BLOCKED: official MCP Python SDK 1.30.0 is not available in this environment ('+type(e).__name__+')',file=sys.stderr);return 3
    if a.check_install:print('SDK import OK; no server qualification performed');return 0
    u=urlsplit(a.url or '')
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment or u.path!='/mcp':p.error('a verified HTTPS /mcp URL is required')
    token=getpass.getpass('Access token issued for this Lab (not stored): ')
    if not token:return 2
    try:asyncio.run(qualify(a.url,token,a.ca,a.output))
    except Exception as e:
        print('FAIL: '+type(e).__name__+' (inspect locally; token and raw exception omitted)',file=sys.stderr);return 1
    print('SDK qualification passed; results saved');return 0
if __name__=='__main__':raise SystemExit(main())
