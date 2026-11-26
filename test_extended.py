import base64, hashlib, io, json, os, stat, subprocess, sys, zipfile
import pytest
from jsonschema import Draft202012Validator
from lab import TOOLS,call,rpc,decode,sha
from test_lab import cases as legacy_cases

def make_zip(name='a.txt',data=b'hello',mode=None,compression=zipfile.ZIP_DEFLATED):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',compression=compression) as z:
        i=zipfile.ZipInfo(name);i.compress_type=compression
        if mode is not None:i.create_system=3;i.external_attr=mode<<16
        z.writestr(i,data)
    return base64.b64encode(out.getvalue()).decode()

R=lambda i,s:{'id':i,'status':s}
W=lambda i,d,s:{'id':i,'depends_on':d,'status':s}
new_cases=[
 ('math_calculate',{'operation':'divide','a':12,'b':4},'result',3,{'operation':'divide','a':1,'b':0}),
 ('statistics_analyze',{'values':[1,2,3]},'mean',2,{'values':[]}),
 ('correlation_analyze',{'x':[1,2,3],'y':[6,4,2]},'pearson_r',-1,{'x':[1,1],'y':[1,2]}),
 ('regression_analyze',{'x':[1,2,3],'y':[3,5,7]},'slope',2,{'x':[1,1],'y':[1,2]}),
 ('numerical_compare',{'actual':100,'expected':101,'absolute_tolerance':1,'relative_tolerance':0},'matches',True,{'actual':1,'expected':1,'absolute_tolerance':-1,'relative_tolerance':0}),
 ('time_series_analyze',{'values':[1,2,3,4],'window':2},'moving_average',[1.5,2.5,3.5],{'values':[1],'window':2}),
 ('dataset_validate',{'expected':['a','b'],'observed':['a']},'missing',['b'],{'expected':['a','a'],'observed':[]}),
 ('completion_verify',{'required':['A','B'],'observed':[R('A','PASS')]},'not_passed',['B'],{'required':['A','A'],'observed':[]}),
 ('regression_detect',{'before':[R('A','PASS')],'after':[R('A','FAIL')]},'regressed',['A'],{'before':[R('A','PASS')]*2,'after':[]}),
 ('code_structure_analyze',{'source':'import os\ndef f(x):\n if x: return 1\n'},'functions',1,{'source':'def ('}),
 ('artifact_checksum',{'data_base64':'YWJj','expected_sha256':sha('abc')},'matches',True,{'data_base64':'!','expected_sha256':sha('abc')}),
 ('archive_validate',{'data_base64':make_zip()},'valid',True,{'data_base64':'!'}),
 ('equity_drawdown_analyze',{'equity':[100,120,90,110]},'max_drawdown_fraction',0.25,{'equity':[0]}),
 ('exam_results_compare',{'reference':['a','b'],'predicted':['a','c']},'accuracy',0.5,{'reference':['a'],'predicted':['a','b']}),
 ('workflow_readiness',{'steps':[W('a',[],'PASS'),W('b',['a'],'PENDING')]},'ready',['b'],{'steps':[W('a',[],'PASS')]*2}),
]
CASES=legacy_cases+[x[:4] for x in new_cases]
@pytest.mark.parametrize('name,args,key,expected,bad',new_cases,ids=[x[0] for x in new_cases])
def test_new_negative(name,args,key,expected,bad):
    with pytest.raises(ValueError):call(name,bad)
@pytest.mark.parametrize('name,args,key,expected',CASES,ids=[x[0] for x in CASES])
def test_result_repeat_schema(name,args,key,expected):
    v=call(name,args);assert v[key]==pytest.approx(expected) if isinstance(expected,(int,float)) and not isinstance(expected,bool) else v[key]==expected
    assert v==call(name,args)
    spec=TOOLS[name][0];Draft202012Validator.check_schema(spec['inputSchema']);Draft202012Validator.check_schema(spec['outputSchema']);Draft202012Validator(spec['outputSchema']).validate(v)
@pytest.mark.parametrize('name,args,key,expected',CASES,ids=[x[0] for x in CASES])
@pytest.mark.parametrize('kind',['missing','extra','type','oversize'])
def test_input_rejection(name,args,key,expected,kind):
    k=next(iter(args)); a=dict(args)
    if kind=='missing':del a[k]
    elif kind=='extra':a['extra']=1
    elif kind=='type':a[k]=None
    else:a[k]='x'*131073
    with pytest.raises(ValueError):call(name,a)
@pytest.mark.parametrize('req',[{'jsonrpc':'2.0','id':True,'method':'ping'},{'jsonrpc':'2.0','id':{},'method':'ping'},{'jsonrpc':'2.0','id':1,'method':'tools/list','params':{'cursor':'unexpected'}},{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}}, {'jsonrpc':'2.0','id':1,'method':'tools/call','params':[]}])
def test_rpc_invalid(req):assert 'error' in rpc(req)
@pytest.mark.parametrize('s',['{"a":1,"a":2}','{"a":NaN}','{"a":1e999}','{"a":"\\ud800"}','['*25+'0'+']'*25])
def test_decode_rejection(s):
    with pytest.raises((ValueError,UnicodeError)):decode(s)
@pytest.mark.parametrize('name,args,key,expected',[
 ('statistics_analyze',{'values':[3]},'population_stddev',0),
 ('regression_analyze',{'x':[1,2],'y':[3,3]},'r_squared',None),
 ('time_series_analyze',{'values':[2,4],'window':2.0},'moving_average',[3]),
 ('numerical_compare',{'actual':0,'expected':0,'absolute_tolerance':0,'relative_tolerance':0},'matches',True),
 ('dataset_validate',{'expected':[],'observed':[]},'complete',False),
 ('completion_verify',{'required':['a'],'observed':[R('a','PASS'),R('b','PASS')]},'declared_complete',False),
 ('regression_detect',{'before':[R('a','PASS')],'after':[]},'missing',['a']),
 ('code_structure_analyze',{'source':'raise RuntimeError("never executed")'},'syntax_valid',True),
 ('artifact_checksum',{'data_base64':'AA==','expected_sha256':hashlib.sha256(b'\0').hexdigest()},'matches',True),
 ('archive_validate',{'data_base64':make_zip('../evil')},'valid',False),
 ('archive_validate',{'data_base64':make_zip('link',b'../x',stat.S_IFLNK|0o777)},'valid',False),
 ('archive_validate',{'data_base64':make_zip('big',b'x'*200001)},'valid',False),
 ('archive_validate',{'data_base64':'YWJj'},'valid',False),
 ('equity_drawdown_analyze',{'equity':[1]},'max_drawdown_fraction',0),
 ('exam_results_compare',{'reference':['x'],'predicted':['x']},'correct',1),
 ('workflow_readiness',{'steps':[W('a',[],'FAIL'),W('b',['a'],'PASS')]},'inconsistent',['b']),
 ('test_results_analyze',{'results':[R('a','BLOCKED')]},'counts',{'PASS':0,'FAIL':0,'SKIP':0,'UNVERIFIED':0,'BLOCKED':1}),
])
def test_edges(name,args,key,expected):assert call(name,args)[key]==expected

def test_duplicate_dependencies():
    with pytest.raises(ValueError):call('workflow_validate',{'steps':[{'id':'a','depends_on':['b','b']}]})

def test_actual_stdio_all():
    requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'qualification','version':'1'}}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/list'}]
    for i,(name,args,k,v) in enumerate(CASES):requests.append({'jsonrpc':'2.0','id':i+3,'method':'tools/call','params':{'name':name,'arguments':args}})
    for _ in range(2):
        p=subprocess.run([sys.executable,'-B','lab.py'],input='\n'.join(map(json.dumps,requests))+'\n',text=True,capture_output=True,timeout=15,check=True)
        rows=list(map(json.loads,p.stdout.splitlines()));assert len(rows)==len(CASES)+2 and not p.stderr
        assert rows[0]['result']['protocolVersion']=='2025-11-25';assert set(t['name'] for t in rows[1]['result']['tools'])==set(TOOLS)
        for row,(name,args,k,v) in zip(rows[2:],CASES):
            assert not row['result']['isError']; assert row['result']['structuredContent']==call(name,args)
            assert json.loads(row['result']['content'][0]['text'])==row['result']['structuredContent']

def test_no_io_after_import(monkeypatch):
    # Audit hook lives in separate child, denies filesystem writes, network, process starts and execution of input.
    script='''import sys,json,os\nfrom lab import call\nfrom test_extended import CASES\ndef guard(event,args):\n if event in ('os.system','subprocess.Popen','socket.connect','socket.bind','os.remove','os.rename','os.mkdir','os.rmdir','os.chmod','os.symlink','os.link'):raise RuntimeError('side effect '+event)\n if event=='open' and len(args)>2 and isinstance(args[2],int) and args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):raise RuntimeError('write')\nsys.addaudithook(guard)\nfor n,a,k,v in CASES:call(n,a)\nprint('all 23 read-only fixtures passed')'''
    p=subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True,timeout=15,check=True)
    assert p.stdout.strip()=='all 23 read-only fixtures passed'

def test_corrupt_deflate_no_crash():
    z=bytearray(base64.b64decode(make_zip('a',b'hello'*10)))
    z[31:35]=b'\xff'*4
    a={'data_base64':base64.b64encode(z).decode()}
    result=rpc({'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':'archive_validate','arguments':a}})
    assert result['result']['structuredContent']['valid'] is False
    assert rpc({'jsonrpc':'2.0','id':6,'method':'ping'})['result']=={}

def test_duplicate_zip_paths():
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('a.txt','a');z.writestr('A.txt','b')
    result=call('archive_validate',{'data_base64':base64.b64encode(out.getvalue()).decode()})
    assert not result['valid'] and 'duplicate_path' in result['issues']

def test_strict_utf8():
    with pytest.raises(UnicodeError):decode('{"a":1}'.encode('utf-16'))
