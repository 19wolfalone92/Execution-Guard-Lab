"""Synthetic, fixed qualification vectors. Not an externally callable service."""
import base64, hashlib, io, json, zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def cases():
    report = json.loads((ROOT / 'BASELINE_RERUN_RPC.json').read_text())
    fixtures = {}
    for row in report['stdio']:
        req, res = row.get('request', {}), row.get('response', {}).get('result', {})
        if req.get('method') == 'tools/call' and not res.get('isError') and 'structuredContent' in res:
            p = req['params']; fixtures[p['name']] = (p['arguments'], res['structuredContent'])
    assert len(fixtures) == 23
    txt = 'x' * 4096; h = hashlib.sha256(txt.encode()).hexdigest()
    ids = [f'i{i}' for i in range(256)]; vals = list(range(1,257)); a = 'a'*40
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, 'w', compression=zipfile.ZIP_STORED) as z:
        for i in range(128): z.writestr(f'{i}.txt', b'x'*200)
    raw = bytes(range(256))*187 + bytes(range(128))
    assert len(raw) == 48000
    stress = {
        'text_sha256': {'text': txt},
        'evidence_bundle_verify': {'items':[{'id':i,'text':txt,'sha256':h} for i in ids[:16]]},
        'acceptance_evaluate': {'criteria':[{'id':i,'status':'PASS','evidence_text':txt,'evidence_sha256':h} for i in ids[:16]]},
        'workflow_validate': {'steps':[{'id':i,'depends_on':ids[:j]} for j,i in enumerate(ids[:32])]},
        'test_results_analyze': {'results':[{'id':i,'status':'PASS'} for i in ids[:64]]},
        'snapshot_compare': {'before':[{'key':i,'value':'a'*512} for i in ids[:64]],'after':[{'key':i,'value':'b'*512} for i in ids[:64]]},
        'blocker_classify': {'code':'RATE_LIMIT'},
        'release_consistency': {'expected_sha':a,'checks':[{'id':i,'sha':a,'status':'PASS'} for i in ids[:64]]},
        'math_calculate': {'operation':'multiply','a':1e12,'b':-1e12},
        'statistics_analyze': {'values':vals},
        'correlation_analyze': {'x':vals,'y':vals[::-1]},
        'regression_analyze': {'x':vals,'y':[2*i+1 for i in vals]},
        'numerical_compare': {'actual':1e12,'expected':-1e12,'absolute_tolerance':1e12,'relative_tolerance':1},
        'time_series_analyze': {'values':vals,'window':128},
        'dataset_validate': {'expected':ids,'observed':ids[::-1]},
        'completion_verify': {'required':ids[:128],'observed':[{'id':i,'status':'PASS'} for i in ids[:128]]},
        'regression_detect': {'before':[{'id':i,'status':'PASS'} for i in ids[:128]],'after':[{'id':i,'status':'FAIL'} for i in ids[:128]]},
        'code_structure_analyze': {'source':'x=1\n'*4000},
        'artifact_checksum': {'data_base64':base64.b64encode(raw).decode(),'expected_sha256':hashlib.sha256(raw).hexdigest()},
        'archive_validate': {'data_base64':base64.b64encode(zipped.getvalue()).decode()},
        'equity_drawdown_analyze': {'equity':vals[::-1]},
        'exam_results_compare': {'reference':['a'*128]*256,'predicted':['b'*128]*256},
        'workflow_readiness': {'steps':[{'id':i,'depends_on':ids[:j],'status':'PASS'} for j,i in enumerate(ids[:32])]},
    }
    assert set(stress)==set(fixtures)
    out=[]
    for name,(args,expected) in fixtures.items():
        out.extend([{'name':name,'case':'baseline','arguments':args,'expected':expected}, {'name':name,'case':'stress','arguments':stress[name]}, {'name':name,'case':'negative','arguments':{}}])
    return out

def evaluate(c):
    from lab import rpc
    response=rpc({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':c['name'],'arguments':c['arguments']}})
    return response['result']
