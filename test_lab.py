import json, subprocess, sys
import pytest
from lab import TOOLS, call, sha

S='a'*40
cases=[
 ('text_sha256',{'text':'abc'},'sha256','ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'),
 ('evidence_bundle_verify',{'items':[{'id':'x','text':'abc','sha256':sha('abc')}]},'all_match',True),
 ('acceptance_evaluate',{'criteria':[{'id':'A','status':'PASS','evidence_text':'abc','evidence_sha256':sha('abc')}]},'declared_pass_with_matching_digest',True),
 ('workflow_validate',{'steps':[{'id':'b','depends_on':['a']},{'id':'a','depends_on':[]}]},'topological_order',['a','b']),
 ('test_results_analyze',{'results':[{'id':'x','status':'PASS'}]},'all_reported_pass',True),
 ('snapshot_compare',{'before':[{'key':'a','value':'1'}],'after':[{'key':'a','value':'2'}]},'changed',['a']),
 ('blocker_classify',{'code':'POLICY_DENIED'},'recommendation','stop_and_seek_official_resolution'),
 ('release_consistency',{'expected_sha':S,'checks':[{'id':'x','sha':S,'status':'PASS'}]},'consistent',True),
]
@pytest.mark.parametrize('name,args,key,expected',cases)
def test_good(name,args,key,expected):assert call(name,args)[key]==expected
@pytest.mark.parametrize('name,args,key,expected',cases)
def test_missing(name,args,key,expected):
    with pytest.raises(ValueError):call(name,{})
@pytest.mark.parametrize('name,args,key,expected',cases)
def test_extra(name,args,key,expected):
    with pytest.raises(ValueError):call(name,{**args,'unexpected':True})
@pytest.mark.parametrize('name,args,key,expected',cases)
def test_wrong_type(name,args,key,expected):
    with pytest.raises(ValueError):call(name,{**args,next(iter(args)):None})
@pytest.mark.parametrize('name',TOOLS)
def test_annotations(name):assert TOOLS[name][0]['annotations']==dict(readOnlyHint=True,destructiveHint=False,openWorldHint=False,idempotentHint=True)
@pytest.mark.parametrize('name,args,key,expected',[
 ('evidence_bundle_verify',{'items':[]},'all_match',False),
 ('evidence_bundle_verify',{'items':[{'id':'x','text':'abc','sha256':'0'*64}]},'all_match',False),
 ('acceptance_evaluate',{'criteria':[{'id':'A','status':'PASS','evidence_text':'abc','evidence_sha256':'0'*64}]},'declared_pass_with_matching_digest',False),
 ('acceptance_evaluate',{'criteria':[]},'declared_pass_with_matching_digest',False),
 ('workflow_validate',{'steps':[{'id':'a','depends_on':['a']}]},'reason','cycle'),
 ('workflow_validate',{'steps':[{'id':'a','depends_on':['b']}]},'reason','unknown_dependency'),
 ('workflow_validate',{'steps':[]},'valid',False),
 ('test_results_analyze',{'results':[{'id':'x','status':'SKIP'}]},'all_reported_pass',False),
 ('test_results_analyze',{'results':[]},'all_reported_pass',False),
 ('blocker_classify',{'code':'UNKNOWN'},'recommendation','diagnose_without_retry'),
 ('blocker_classify',{'code':'PERMISSION_DENIED'},'recommendation','stop_and_verify_authorization'),
 ('release_consistency',{'expected_sha':S,'checks':[{'id':'x','sha':'b'*40,'status':'PASS'}]},'consistent',False),
 ('release_consistency',{'expected_sha':S,'checks':[]},'consistent',False),
])
def test_negative_cases(name,args,key,expected):assert call(name,args)[key]==expected

def test_bounds():
    with pytest.raises(ValueError):call('text_sha256',{'text':'x'*4097})
def test_duplicates():
    with pytest.raises(ValueError):call('workflow_validate',{'steps':[{'id':'a','depends_on':[]}]*2})
def test_unknown_tool():
    with pytest.raises(ValueError):call('shell_execute',{})
def test_stdio_roundtrip():
    reqs=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26'}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/list'}]
    reqs += [{'jsonrpc':'2.0','id':i+3,'method':'tools/call','params':{'name':n,'arguments':a}} for i,(n,a,_,_) in enumerate(cases)]
    reqs += [{'jsonrpc':'2.0','id':99,'method':'tools/call','params':{'name':'shell_execute','arguments':{}}}]
    p=subprocess.run([sys.executable,'lab.py'],input='\n'.join(map(json.dumps,reqs))+'\n',text=True,capture_output=True,check=True,timeout=10)
    rows=list(map(json.loads,p.stdout.splitlines()));assert len(rows)==11
    assert rows[0]['result']['protocolVersion']=='2025-03-26'
    assert {t['name'] for t in rows[1]['result']['tools']}==set(TOOLS)
    for r,(_,_,k,v) in zip(rows[2:-1],cases):assert not r['result']['isError'] and json.loads(r['result']['content'][0]['text'])[k]==v
    assert rows[-1]['result']['isError']

def test_invalid_identifier_newline():
    with pytest.raises(ValueError):call('workflow_validate',{'steps':[{'id':'a\n','depends_on':[]}]})
def test_malformed_unicode():
    with pytest.raises(ValueError):call('text_sha256',{'text':'\ud800'})
def test_bad_transport_and_recovery():
    good=json.dumps({'jsonrpc':'2.0','id':7,'method':'ping'})
    p=subprocess.run([sys.executable,'lab.py'],input='not-json\n'+'x'*(128*1024+10)+'\n'+good+'\n',text=True,capture_output=True,check=True,timeout=10)
    rows=list(map(json.loads,p.stdout.splitlines())); assert len(rows)==3
    assert rows[0]['error']['code']==-32700 and rows[1]['error']['message']=='request_too_large' and rows[2]['result']=={}
