"""Reconstruct the integrated 115 and produce independent expected values."""
import csv
from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from cloud_runtime.cases import cases, evaluate

def stresses(source, baseline):
    ordered = lambda n: [f'i{i}' for i in range(n)]
    result = {
        'text_sha256': {'sha256': hashlib.sha256(b'x' * 4096).hexdigest()},
        'evidence_bundle_verify': {'all_match': True, 'items': [{'id':i,'matches':True} for i in ordered(16)]},
        'acceptance_evaluate': {'criteria': [{'id':i,'status':'PASS','digest_matches':True} for i in ordered(16)],
                                'declared_pass_with_matching_digest': True},
        'workflow_validate': {'valid':True, 'topological_order':ordered(32), 'reason':None},
        'test_results_analyze': {'counts':{'PASS':64,'FAIL':0,'SKIP':0,'UNVERIFIED':0,'BLOCKED':0}, 'all_reported_pass':True},
        'snapshot_compare': {'added':[], 'removed':[], 'changed':sorted(ordered(64))},
        'blocker_classify': {'category':'transient', 'recommendation':'respect_retry_after_if_authorized','executes_retry':False},
        'release_consistency': {'consistent':True, 'checks':[{'id':i,'matches_sha':True,'reported_pass':True} for i in ordered(64)]},
        'math_calculate': {'result': -1e24},
        'statistics_analyze': {'count':256,'mean':128.5,'median':128.5,'min':1,'max':256,'population_stddev':math.sqrt((256**2-1)/12)},
        'correlation_analyze': {'pearson_r':-1,'count':256},
        'regression_analyze': {'slope':2,'intercept':1,'r_squared':1,'count':256},
        'numerical_compare': {'matches':False,'absolute_error':2*10**12,'limit':10**12},
        'time_series_analyze': {'moving_average':[64.5+i for i in range(129)],'changes':[1]*255,'window':128},
        'dataset_validate': {'missing':[],'unexpected':[],'matched':sorted(ordered(256)),'complete':True},
        'completion_verify': {'missing':[],'unexpected':[],'not_passed':[],'declared_complete':True},
        'regression_detect': {'regressed':sorted(ordered(128)),'improved':[],'missing':[],'new':[]},
        'code_structure_analyze': {'syntax_valid':True,'nodes':1+4000*4,'functions':0,'branch_nodes':0,'import_roots':[]},
        'artifact_checksum': {'bytes':48000,'sha256':source['artifact_checksum']['expected_sha256'],'matches':True},
        'archive_validate': {'valid':True,'entries':128,'expanded_bytes':25600,'issues':[]},
        'equity_drawdown_analyze': {'max_drawdown_fraction':255/256,'peak_index':0,'trough_index':255},
        'exam_results_compare': {'correct':0,'total':256,'accuracy':0,'mismatch_indices':list(range(256))},
        'workflow_readiness': {'graph_valid':True,'ready':[],'inconsistent':[]},
    }
    for name, expected in result.items():
        if 'scope' in baseline[name]:
            expected['scope'] = baseline[name]['scope']
    return result

def exact_math(name, a):
    if name == 'math_calculate':
        x,y = Fraction(a['a']), Fraction(a['b'])
        if a['operation'] == 'divide':
            return {'result':float(x/y)}
        value = {'add':x+y, 'subtract':x-y, 'multiply':x*y}[a['operation']]
        return {'result':int(value) if all(type(a[k]) is int for k in ('a','b')) else float(value)}
    if name == 'statistics_analyze':
        values = sorted(map(Fraction,a['values']))
        count = len(values)
        mean = sum(values)/count
        median = (values[count//2]+values[(count-1)//2])/2
        variance = sum((i-mean)**2 for i in values)/count
        return {'count':count,'mean':float(mean),'median':float(median),
                'population_stddev':math.sqrt(variance),'min':float(values[0]),'max':float(values[-1])}
    if name in ('correlation_analyze','regression_analyze'):
        # Independent normal equations with rational sums and Cauchy-Schwarz.
        x, y = list(map(Fraction,a['x'])), list(map(Fraction,a['y']))
        n = len(x)
        sx, sy = sum(x), sum(y)
        vx = n * sum(i*i for i in x) - sx*sx
        vy = n * sum(i*i for i in y) - sy*sy
        cross = n * sum(i*j for i,j in zip(x,y)) - sx*sy
        if name == 'correlation_analyze':
            magnitude = math.sqrt(cross*cross/(vx*vy))
            return {'pearson_r':-magnitude if cross<0 else magnitude,'count':n}
        slope = cross/vx
        return {'slope':float(slope),'intercept':float((sy-slope*sx)/n),
                'r_squared':float(cross*cross/(vx*vy)) if vy else None,'count':n}
    if name == 'time_series_analyze':
        values = list(map(Fraction,a['values']))
        n = a['window']
        positions = range(n, len(values)+1)
        return {'moving_average':[float(sum(values[i-n:i])/n) for i in positions],
                'changes':[float(b-a) for a,b in zip(values,values[1:])],'window':n}
    raise ValueError(name)

def edge_cases():
    tiny = float.fromhex('0x0.0000000000001p-1022')
    for name, args in [
        ('math_calculate',{'a':10**12-1,'b':-(10**12-3),'operation':'multiply'}),
        ('math_calculate',{'a':-1e12,'b':1e12,'operation':'subtract'}),
        ('math_calculate',{'a':7,'b':-3,'operation':'divide'}),
        ('math_calculate',{'a':0,'b':-7,'operation':'add'}),
        ('statistics_analyze',{'values':[-1e12,0,-1,1e12,0.125,-0.25]}),
        ('statistics_analyze',{'values':[0.1,0.2,0.1,-0.4]}),
        ('statistics_analyze',{'values':[7]}),
        ('correlation_analyze',{'x':[1e12-3,1e12-2,1e12-1,1e12],'y':[-7,1,-3,9]}),
        ('correlation_analyze',{'x':[-2,1,2,4],'y':[9,1,2,-8]}),
        ('regression_analyze',{'x':[-2,-1,0,1,2],'y':[1,0,-2,3,2]}),
        ('regression_analyze',{'x':[1,2],'y':[3,3]}),
        ('time_series_analyze',{'values':[-7.5,0,1.1,4.2,12],'window':3}),
        ('time_series_analyze',{'values':[1e12,-1e12,0],'window':1}),
    ]:
        yield name, args, exact_math(name,args), 'Independent Fraction arithmetic and closed-form reference'
    txt='🐺\né\tβ𝕊'
    yield 'text_sha256', {'text':txt}, {'sha256':hashlib.sha256(txt.encode()).hexdigest()}, 'Native SHA-256 UTF-8'
    for name,args,error in [
        ('math_calculate',{'a':1,'b':0,'operation':'divide'},'division_by_zero'),
        ('math_calculate',{'a':-1e12,'b':tiny,'operation':'divide'},'nonfinite_number'),
        ('math_calculate',{'a':True,'b':1,'operation':'add'},'invalid_arguments'),
        ('math_calculate',{'a':1_000_000_000_001,'b':1,'operation':'add'},'invalid_arguments'),
        ('statistics_analyze',{'values':[]},'invalid_arguments'),
        ('statistics_analyze',{'values':[{'value':1}]},'invalid_arguments'),
        ('correlation_analyze',{'x':[1,1],'y':[0,2]},'constant_series'),
        ('correlation_analyze',{'x':[1,2,3],'y':[1,2]},'length_mismatch'),
        ('regression_analyze',{'x':[2,2],'y':[1,2]},'constant_predictor'),
        ('time_series_analyze',{'values':[1],'window':2},'window_exceeds_series'),
        ('dataset_validate',{'expected':['x','x'],'observed':[]},'duplicate_identifier'),
        ('text_sha256',{'text':'a'*4097},'invalid_arguments'),
        ('text_sha256',{'text':'abc','extra':{}},'invalid_arguments'),
        ('code_structure_analyze',{'source':'x='+'('*81+'1'+')'*81},'ast_complexity_limit'),
        ('code_structure_analyze',{'source':'def ('},'invalid_python_syntax'),
        ('artifact_checksum',{'data_base64':'AB==','expected_sha256':'0'*64},'invalid_base64'),
    ]:
        yield name, args, error, 'Schema, mathematical domain or resource bound'
    for name,args,expected in [
        ('numerical_compare',{'actual':0,'expected':0,'absolute_tolerance':0,'relative_tolerance':0},
         {'matches':True,'absolute_error':0,'limit':0}),
        ('equity_drawdown_analyze',{'equity':[100, 120, 90, 130, 100]},
         {'max_drawdown_fraction':1/4,'peak_index':1,'trough_index':2,'scope':'supplied_equity_curve_only'}),
        ('code_structure_analyze',{'source':'raise RuntimeError("inert data")'},
         {'syntax_valid':True,'nodes':6,'functions':0,'branch_nodes':0,'import_roots':[],
          'scope':'python_ast_only_not_execution_or_full_complexity'}),
    ]:
        yield name,args,expected,'Hand-derived independent reference'
    for name, data, compression, valid, issues in [
        ('a.txt', b'abc', zipfile.ZIP_DEFLATED, True, []),
        ('../unexpected', b'a', zipfile.ZIP_STORED, False, ['unsafe_path']),
        ('expanded', b'x'*200001, zipfile.ZIP_DEFLATED, False, ['expansion_limit']),
    ]:
        import base64
        stream = io.BytesIO()
        with zipfile.ZipFile(stream,'w',compression=compression) as z:
            z.writestr(zipfile.ZipInfo(name),data,compress_type=compression)
        yield 'archive_validate', {'data_base64':base64.b64encode(stream.getvalue()).decode()}, {
            'valid':valid,'entries':1,'expanded_bytes':len(data),'issues':issues,
            'scope':'bounded_zip_structure_and_crc_not_malware_scan',
        }, 'Independent constructed ZIP headers and data'

def generate():
    corpus = cases()
    base = {c['name']:c['expected'] for c in corpus if c['case']=='baseline'}
    stress = {c['name']:c['arguments'] for c in corpus if c['case']=='stress'}
    independent = stresses(stress,base)
    rows = []
    for session in (1,2):
        for c in corpus:
            kind, name = c['case'],c['name']
            if session == 2 and kind == 'stress':
                continue
            if kind == 'stress':
                reference = evaluate(c)['structuredContent']
                assert_equal(independent[name], reference)
                expected, source = independent[name], 'Independent stress oracle and original Python comparison'
            elif kind == 'baseline':
                expected, source = c['expected'], 'Committed known results from BASELINE_RERUN_RPC.json'
                if name in {'math_calculate','statistics_analyze','correlation_analyze','regression_analyze','time_series_analyze'}:
                    assert_equal(exact_math(name,c['arguments']),expected)
                    source += ' and independent rational oracle'
            else:
                expected, source = 'invalid_arguments', 'Original missing arguments, confirmed schema'
            rows.append(dict(tool=name, inputs=c['arguments'],expected=expected,oracle=source,case=kind,session=session))
    assert len(rows) == 115
    for name,args,expected,source in edge_cases():
        rows.append(dict(tool=name,inputs=args,expected=expected,oracle=source,case='edge',session=1))
    return [dict(id=f'{"H" if i<115 else "E"}{i+1 if i<115 else i-114:03}', **row) for i,row in enumerate(rows)]

def assert_equal(actual, expected):
    if type(expected) is dict:
        assert type(actual) is dict and actual.keys()==expected.keys(), (actual,expected)
        for k,v in expected.items():
            assert_equal(actual[k],v)
    elif type(expected) is list:
        assert type(actual) is list and len(actual)==len(expected), (actual,expected)
        for a,b in zip(actual,expected):
            assert_equal(a,b)
    elif type(expected) is float:
        assert type(actual) in (int,float) and math.isclose(actual,expected,rel_tol=2e-14,abs_tol=1e-15), (actual,expected)
    else:
        assert actual == expected and (type(expected) is not bool or type(actual) is bool), (actual,expected)

def compare(path, fixtures, out):
    revision = json.loads(Path(path).read_text())
    vectors = {case['id']:case for case in json.loads(Path(fixtures).read_text())}
    assert set(vectors) == {r['id'] for r in revision['rows']}
    results = []
    unique = set()
    for r in revision['rows']:
        case = vectors[r['id']]
        try:
            assert r['status'] == 200, (r['status'], r['wire'][:160])
            inner = json.loads(r['wire'])['result']
            expected = case['expected']
            if isinstance(expected,str):
                assert inner['isError'] is True, inner
                msg, request_id = inner['content'][0]['text'].split(' Request ID ',1)
                assert msg == expected, (msg,expected)
            else:
                assert inner['isError'] is False, inner
                obj = inner['structuredContent']
                assert json.loads(inner['content'][0]['text']) == obj
                request_id = obj.pop('request_id')
                if type(expected.get('result')) is int and abs(expected['result'])>2**53-1:
                    assert obj.pop('exact_integer') == str(expected['result'])
                assert_equal(obj,expected)
            from uuid import UUID
            assert UUID(request_id).version == 4 and request_id not in unique
            unique.add(request_id)
            verdict, detail = 'PASS',request_id
        except (AssertionError, ValueError, KeyError, TypeError) as exc:
            verdict, detail = 'FAIL',str(exc)[:500]
        results.append({'id':case['id'],'session':case['session'],'tool':case['tool'],'case':case['case'],
                        'oracle':case['oracle'],'status':verdict,'request_id_or_failure':detail,
                        'http':r['status'],'response_bytes':r['response_bytes'],'client_ms':r['client_ms']})
    for tag, filename in (('H','115-SCENARIOS.csv'),('E','BOUNDARY-CASES.csv')):
        rows = [r for r in results if r['id'].startswith(tag)]
        with (Path(out)/filename).open('w',encoding='utf-8',newline='') as f:
            w = csv.DictWriter(f,fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        failed = [r for r in rows if r['status']!='PASS']
        print(filename,len(rows)-len(failed),'/',len(rows),'passed')
        for failure in failed:
            print(failure['id'],failure['tool'],failure['request_id_or_failure'])
    return 1 if any(r['status']!='PASS' for r in results) else 0

if __name__ == '__main__':
    if sys.argv[1] == 'generate':
        rows = generate()
        for r in rows:
            r['wire_arguments'] = json.dumps(r['inputs'],ensure_ascii=True,allow_nan=False,separators=(',',':'))
        Path(sys.argv[2]).write_text(json.dumps(rows,ensure_ascii=True,allow_nan=False,separators=(',',':')))
    else:
        sys.exit(compare(sys.argv[2],sys.argv[3],sys.argv[4]))
