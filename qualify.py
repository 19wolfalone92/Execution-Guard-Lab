"""Independent local process readback. Uses synthetic fixtures only; writes report to stdout."""
import json, subprocess, sys, http.client, hashlib
from test_extended import CASES, new_cases
from pathlib import Path

def run():
    messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'eg-lab-qualification','version':'1'}}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/list'}]
    for i,(name,args,k,v) in enumerate(CASES):messages.append({'jsonrpc':'2.0','id':i+3,'method':'tools/call','params':{'name':name,'arguments':args}})
    for i,(name,args,k,v) in enumerate(CASES):messages.append({'jsonrpc':'2.0','id':100+i,'method':'tools/call','params':{'name':name,'arguments':{}}})
    expected={i+3:(n,k,v) for i,(n,a,k,v) in enumerate(CASES)}
    def verify(r):
        rid=r['id']
        if rid==1: assert r['result']['serverInfo']['version']=='0.2.0'
        elif rid==2:assert {t['name'] for t in r['result']['tools']}=={x[0] for x in CASES}
        elif rid>=100:assert r['result']['isError'] is True
        else:
            name,key,value=expected[rid];result=r['result'];assert result['isError'] is False
            actual=result['structuredContent'][key]
            if isinstance(value,(int,float)) and not isinstance(value,bool):assert abs(actual-value)<=1e-12
            else:assert actual==value
            assert json.loads(result['content'][0]['text'])==result['structuredContent']
    out={'scope':'synthetic local independent process checks only; not ChatGPT calls','stdio':[],'http':[]}
    for repeat in range(2):
        p=subprocess.run([sys.executable,'-B','lab.py'],input='\n'.join(map(json.dumps,messages))+'\n',text=True,capture_output=True,timeout=15,check=True)
        rows=list(map(json.loads,p.stdout.splitlines()));assert len(rows)==len(messages)-1 and not p.stderr
        for req,r in zip([m for m in messages if 'id' in m],rows):
            verify(r);out['stdio'].append({'repeat':repeat+1,'request':req,'response':r,'state':'PASS'})
    for repeat in range(2):
        p=subprocess.Popen([sys.executable,'-B','http_lab.py','--port','0'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            port=json.loads(p.stdout.readline())['port']
            for req in messages:
                c=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
                try:
                    c.request('POST','/mcp',body=json.dumps(req),headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-11-25'})
                    resp=c.getresponse();raw=resp.read();r=json.loads(raw) if raw else None
                    if 'id' not in req:assert resp.status==202 and r is None
                    else:assert resp.status==200;verify(r)
                    out['http'].append({'repeat':repeat+1,'request':req,'http_status':resp.status,'response':r,'state':'PASS'})
                finally:c.close()
        finally:p.terminate();p.communicate(timeout=5)
    out['counts']={k:len(out[k]) for k in ('stdio','http')}
    return out
if __name__=='__main__':print(json.dumps(run(),ensure_ascii=False,indent=2,allow_nan=False))
