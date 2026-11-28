"""Local stdio MCP-shaped lab. No network, subprocesses, or persistent writes."""
import hashlib, json, re, sys, math
from collections import Counter
from jsonschema import Draft202012Validator

MAX_LINE = 128 * 1024
HEX = r'^[0-9a-f]{64}(?![\s\S])'
GIT = r'^[0-9a-f]{40}(?![\s\S])'
KEY = r'^[a-zA-Z0-9_.-]{1,64}(?![\s\S])'
def string(n=4096, pattern=None):
    return {'type':'string','maxLength':n,**({'pattern':pattern} if pattern else {})}
def obj(**p): return {'type':'object','properties':p,'required':list(p),'additionalProperties':False}
def arr(item, n=64): return {'type':'array','items':item,'maxItems':n}
def enum(*values): return {'type':'string','enum':list(values)}
def sha(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()
def unique(rows, key):
    ids=[r[key] for r in rows]
    if len(set(ids)) != len(ids): raise ValueError('duplicate_identifier')
    return ids

def digest(text): return {'sha256':sha(text)}
def evidence(items):
    unique(items,'id')
    rows=[{'id':i['id'],'matches':sha(i['text'])==i['sha256']} for i in items]
    return {'all_match':bool(rows) and all(r['matches'] for r in rows),'items':rows,'scope':'supplied_text_integrity_only'}
def acceptance(criteria):
    unique(criteria,'id')
    rows=[]
    for r in criteria:
        matched=bool(r['evidence_text']) and sha(r['evidence_text'])==r['evidence_sha256']
        status=r['status'] if r['status']!='PASS' or matched else 'UNVERIFIED'
        rows.append({'id':r['id'],'status':status,'digest_matches':matched})
    return {'criteria':rows,'declared_pass_with_matching_digest':bool(rows) and all(r['status']=='PASS' for r in rows),'scope':'declarations_and_digest_only_not_independent_acceptance'}
def workflow(steps):
    for step in steps:
        if len(set(step['depends_on'])) != len(step['depends_on']): raise ValueError('duplicate_dependency')
    ids=set(unique(steps,'id'))
    unknown=sorted({d for s in steps for d in s['depends_on'] if d not in ids})
    if unknown:return {'valid':False,'reason':'unknown_dependency','unknown':unknown}
    pending={s['id']:set(s['depends_on']) for s in steps}; order=[]
    while pending:
        ready=sorted(k for k,v in pending.items() if not v)
        if not ready:return {'valid':False,'reason':'cycle','unresolved':sorted(pending)}
        order.extend(ready)
        for k in ready:del pending[k]
        for v in pending.values():v.difference_update(ready)
    return {'valid':bool(order),'topological_order':order,'reason':None if order else 'empty_workflow'}
def tests(results):
    unique(results,'id'); counts=Counter(r['status'] for r in results)
    return {'counts':{k:counts[k] for k in ('PASS','FAIL','SKIP','UNVERIFIED','BLOCKED')},'all_reported_pass':bool(results) and counts['PASS']==len(results),'scope':'supplied_results_only'}
def snapshot(before,after):
    unique(before,'key');unique(after,'key')
    a={r['key']:r['value'] for r in before};b={r['key']:r['value'] for r in after}
    return {'added':sorted(b.keys()-a.keys()),'removed':sorted(a.keys()-b.keys()),'changed':sorted(k for k in a.keys()&b.keys() if a[k]!=b[k])}
def blocker(code):
    category,action={
      'POLICY_DENIED':('policy','stop_and_seek_official_resolution'),
      'PERMISSION_DENIED':('authorization','stop_and_verify_authorization'),
      'UNKNOWN':('unknown','diagnose_without_retry'),
      'TIMEOUT':('transient','evaluate_bounded_retry_if_authorized'),
      'RATE_LIMIT':('transient','respect_retry_after_if_authorized'),
      'INVALID_INPUT':('validation','correct_input_before_retry'),
      'TEST_FAILURE':('quality','diagnose_failure_before_retry')}[code]
    return {'category':category,'recommendation':action,'executes_retry':False}
def release(expected_sha,checks):
    unique(checks,'id'); rows=[{'id':r['id'],'matches_sha':r['sha']==expected_sha,'reported_pass':r['status']=='PASS'} for r in checks]
    return {'checks':rows,'consistent':bool(rows) and all(r['matches_sha'] and r['reported_pass'] for r in rows),'scope':'supplied_metadata_only_not_live_ci'}

TOOLS={}
def register(name,description,schema,fn):
    Draft202012Validator.check_schema(schema)
    TOOLS[name]=({'name':name,'description':description,'inputSchema':schema,'annotations':{'readOnlyHint':True,'destructiveHint':False,'openWorldHint':False,'idempotentHint':True}},fn)
    return TOOLS[name][0]
register('text_sha256','Compute SHA-256 of provided UTF-8 text.',obj(text=string()),digest)
register('evidence_bundle_verify','Compare supplied evidence text against supplied digests; does not establish provenance.',obj(items=arr(obj(id=string(64,KEY),text=string(),sha256=string(64,HEX)),16)),evidence)
register('acceptance_evaluate','Evaluate declared acceptance statuses and evidence digests, not external facts.',obj(criteria=arr(obj(id=string(64,KEY),status=enum('PASS','FAIL','BLOCKED','UNVERIFIED'),evidence_text=string(),evidence_sha256=string(64,HEX)),16)),acceptance)
register('workflow_validate','Check supplied dependency graph for missing references and cycles; never executes steps.',obj(steps=arr(obj(id=string(64,KEY),depends_on=arr(string(64,KEY),32)),32)),workflow)
register('test_results_analyze','Count supplied test outcomes, without running tests.',obj(results=arr(obj(id=string(64,KEY),status=enum('PASS','FAIL','SKIP','UNVERIFIED','BLOCKED')))),tests)
row=obj(key=string(64,KEY),value=string(512))
register('snapshot_compare','Compare keys and values of two supplied snapshots without saving either.',obj(before=arr(row),after=arr(row)),snapshot)
register('blocker_classify','Classify a supplied error code; policy denials must stop pending official resolution.',obj(code=enum('POLICY_DENIED','PERMISSION_DENIED','UNKNOWN','TIMEOUT','RATE_LIMIT','INVALID_INPUT','TEST_FAILURE')),blocker)
register('release_consistency','Compare supplied CI commit identifiers and reported outcomes, without querying CI.',obj(expected_sha=string(40,GIT),checks=arr(obj(id=string(64,KEY),sha=string(40,GIT),status=enum('PASS','FAIL','PENDING')))),release)

if __name__=="__main__":sys.modules["lab"]=sys.modules[__name__]
from extensions import install
install(register, obj, arr, string, enum, KEY, HEX)

# Explicit object output schemas for legacy tools; validate successful results.
B={'type':'boolean'}; N={'type':'integer','minimum':0}; T={'type':'string'}
legacy={
 'text_sha256':obj(sha256=string(64,HEX)),
 'evidence_bundle_verify':obj(all_match=B,items=arr(obj(id=T,matches=B)),scope=T),
 'acceptance_evaluate':obj(criteria=arr(obj(id=T,status=T,digest_matches=B)),declared_pass_with_matching_digest=B,scope=T),
 'workflow_validate':{'type':'object','properties':{'valid':B,'reason':{'type':['string','null']},'unknown':arr(T,1024),'unresolved':arr(T),'topological_order':arr(T)},'required':['valid','reason'],'additionalProperties':False},
 'test_results_analyze':obj(counts=obj(**{k:N for k in ('PASS','FAIL','SKIP','UNVERIFIED','BLOCKED')}),all_reported_pass=B,scope=T),
 'snapshot_compare':obj(added=arr(T),removed=arr(T),changed=arr(T)),
 'blocker_classify':obj(category=T,recommendation=T,executes_retry=B),
 'release_consistency':obj(checks=arr(obj(id=T,matches_sha=B,reported_pass=B)),consistent=B,scope=T)}
for name,schema in legacy.items(): TOOLS[name][0]['outputSchema']=schema
for spec,_ in TOOLS.values(): Draft202012Validator.check_schema(spec['outputSchema'])

def check_data(v,depth=0):
    if depth>20:raise ValueError('data_depth_limit')
    if isinstance(v,str):v.encode('utf-8','strict')
    elif isinstance(v,float) and not math.isfinite(v):raise ValueError('nonfinite_number')
    elif isinstance(v,dict):
        for k,x in v.items():check_data(k,depth+1);check_data(x,depth+1)
    elif isinstance(v,list):
        for x in v:check_data(x,depth+1)

def call(name,args):
    if not isinstance(name,str) or name not in TOOLS: raise ValueError('unknown_tool')
    spec,fn=TOOLS[name]
    try:
        check_data(args)
        if len(json.dumps(args,ensure_ascii=False,allow_nan=False).encode())>MAX_LINE:raise ValueError('request_too_large')
        if not Draft202012Validator(spec['inputSchema']).is_valid(args):raise ValueError('invalid_arguments')
        result=fn(**args)
        check_data(result)
        if not Draft202012Validator(spec['outputSchema']).is_valid(result):raise ValueError('invalid_internal_output')
        return result
    except UnicodeError:raise ValueError('invalid_unicode') from None

def rpc(req):
    def err(code,msg,rid=None):return {'jsonrpc':'2.0','id':rid,'error':{'code':code,'message':msg}}
    if not isinstance(req,dict):return err(-32600,'invalid_request')
    rid=req.get('id');method=req.get('method');p=req.get('params',{})
    if ('id' in req and type(rid) not in (str,int)) or req.get('jsonrpc')!='2.0' or not isinstance(method,str):return err(-32600,'invalid_request')
    if not isinstance(p,dict):return err(-32602,'invalid_params',rid) if 'id' in req else None
    if 'id' not in req:return None
    if method=='initialize':
        if not isinstance(p.get('protocolVersion'),str):return err(-32602,'invalid_params',rid)
        supported=('2025-03-26','2025-06-18','2025-11-25')
        result={'protocolVersion':p['protocolVersion'] if p['protocolVersion'] in supported else supported[-1],'capabilities':{'tools':{}},'serverInfo':{'name':'execution-guard-lab','version':'0.2.0'}}
    elif method=='ping':result={}
    elif method=='tools/list':
        if p.get('cursor') is not None:return err(-32602,'invalid_cursor',rid)
        result={'tools':[v[0] for v in TOOLS.values()]}
    elif method=='tools/call':
        if not isinstance(p.get('name'),str):return err(-32602,'invalid_tool_name',rid)
        try:
            value=call(p['name'],p.get('arguments',{}))
            result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=True,allow_nan=False)}],'structuredContent':value,'isError':False}
        except ValueError as e:
            # Never include arbitrary exception text or caller data.
            msg=str(e) if re.fullmatch(r'[a-z_]{1,64}',str(e)) else 'invalid_arguments'
            result={'content':[{'type':'text','text':msg}],'isError':True}
        except (ArithmeticError,RecursionError):result={'content':[{'type':'text','text':'computation_limit'}],'isError':True}
    else:return err(-32601,'method_not_found',rid)
    return {'jsonrpc':'2.0','id':rid,'result':result}

def decode(line):
    if isinstance(line,bytes):line=line.decode("utf-8","strict")
    def pairs(xs):
        d={}
        for k,v in xs:
            if k in d:raise ValueError('duplicate_json_key')
            d[k]=v
        return d
    def reject(s):raise ValueError('nonfinite_number')
    value=json.loads(line,object_pairs_hook=pairs,parse_constant=reject)
    check_data(value)
    return value

def main():
    while True:
        line=sys.stdin.buffer.readline(MAX_LINE+1)
        if not line:break
        if len(line)>MAX_LINE:
            if not line.endswith(b'\n'):
                while line and not line.endswith(b'\n'):line=sys.stdin.buffer.readline(MAX_LINE+1)
            out={'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'request_too_large'}}
        else:
            try:out=rpc(decode(line))
            except (ValueError,RecursionError,UnicodeError):out={'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'invalid_json'}}
        if out is not None:print(json.dumps(out,ensure_ascii=True),flush=True)
if __name__=='__main__':main()
