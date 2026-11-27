"""Native differential/resource qualification for the 23-tool registry.
Boundary examples maximize specified dimensions, not every possible value or
UTF-8 encoding. Never equate native CPU or tracemalloc to cloud billing.
"""
import base64,csv,hashlib,io,json,math,statistics,sys,time,tracemalloc,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import lab
from cloud_runtime.cases import cases,evaluate
from integrated.core.src.optimized import install

def boundary_cases():
    ids=[f'i{i:063d}' for i in range(256)];txt='x'*4096;h=hashlib.sha256(txt.encode()).hexdigest();g='a'*40
    values=[(-1 if i%2 else 1)*(1e12-i-0.25) for i in range(256)]
    def zdata(fill):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w',compression=zipfile.ZIP_STORED) as z:
            for i in range(128):z.writestr(zipfile.ZipInfo(f'{i:03d}.txt',(2026,1,1,0,0,0)),b'x'*(fill if i==0 else 0))
        return b.getvalue()
    archive=zdata(48000-len(zdata(0)));assert len(archive)==48000
    raw=bytes(range(256))*187+bytes(range(128));assert len(raw)==48000
    data={
      'text_sha256':{'text':txt},'evidence_bundle_verify':{'items':[{'id':i,'text':txt,'sha256':h} for i in ids[:16]]},
      'acceptance_evaluate':{'criteria':[{'id':i,'status':'PASS','evidence_text':txt,'evidence_sha256':h} for i in ids[:16]]},
      'workflow_validate':{'steps':[{'id':i,'depends_on':ids[:j]} for j,i in enumerate(ids[:32])]},
      'test_results_analyze':{'results':[{'id':i,'status':'UNVERIFIED'} for i in ids[:64]]},
      'snapshot_compare':{'before':[{'key':i,'value':'a'*512} for i in ids[:64]],'after':[{'key':i,'value':'b'*512} for i in ids[:64]]},
      'blocker_classify':{'code':'PERMISSION_DENIED'},'release_consistency':{'expected_sha':g,'checks':[{'id':i,'sha':g,'status':'PASS'} for i in ids[:64]]},
      'math_calculate':{'operation':'multiply','a':1e12,'b':-1e12},'statistics_analyze':{'values':values},'correlation_analyze':{'x':values,'y':values[::-1]},
      'regression_analyze':{'x':values,'y':values[::-1]},'numerical_compare':{'actual':-1e12,'expected':1e12,'absolute_tolerance':1e12,'relative_tolerance':1},
      'time_series_analyze':{'values':values,'window':128},'dataset_validate':{'expected':ids,'observed':ids[::-1]},
      'completion_verify':{'required':ids[:128],'observed':[{'id':i,'status':'UNVERIFIED'} for i in ids[:128]]},
      'regression_detect':{'before':[{'id':i,'status':'PASS'} for i in ids[:128]],'after':[{'id':i,'status':'UNVERIFIED'} for i in ids[:128]]},
      'code_structure_analyze':{'source':'x=1\n'*4000},'artifact_checksum':{'data_base64':base64.b64encode(raw).decode(),'expected_sha256':hashlib.sha256(raw).hexdigest()},
      'archive_validate':{'data_base64':base64.b64encode(archive).decode()},'equity_drawdown_analyze':{'equity':[1e12-i for i in range(256)]},
      'exam_results_compare':{'reference':['a'*128]*256,'predicted':['b'*128]*256},
      'workflow_readiness':{'steps':[{'id':i,'depends_on':ids[:j],'status':'PASS'} for j,i in enumerate(ids[:32])]},
    }
    assert set(data)==set(lab.TOOLS)
    return [{'name':name,'case':'schema_boundary','arguments':args} for name,args in data.items()]

def pct(xs,p):return sorted(xs)[max(0,math.ceil(p*len(xs))-1)]
def bench(c,n=20):
    start=time.perf_counter_ns();expected=evaluate(c);first=(time.perf_counter_ns()-start)/1e6;wall=[];cpu=[]
    assert bool(expected.get('isError'))==(c['case']=='negative'),(c['name'],c['case'],expected)
    if c['case']=='baseline':assert expected['structuredContent']==c['expected']
    for _ in range(n):
        t=time.perf_counter_ns();cp=time.process_time_ns();r=evaluate(c);cpu.append((time.process_time_ns()-cp)/1e6);wall.append((time.perf_counter_ns()-t)/1e6);assert r==expected,c['name']
    tracemalloc.start();r=evaluate(c);_,peak=tracemalloc.get_traced_memory();tracemalloc.stop();assert r==expected
    return expected,{'samples':n,'first_wall_ms':first,'wall_p50_ms':statistics.median(wall),'wall_p95_ms':pct(wall,.95),'wall_p99_ms':pct(wall,.99),'wall_max_ms':max(wall),'cpu_p50_ms':statistics.median(cpu),'cpu_p95_ms':pct(cpu,.95),'cpu_p99_ms':pct(cpu,.99),'python_alloc_peak_bytes':peak,'request_bytes':len(json.dumps(c['arguments'],ensure_ascii=False).encode()),'response_bytes':len(json.dumps(r,ensure_ascii=True).encode()),'unexpected_errors':0}

def main(output):
    vec=cases()+boundary_cases();old=[bench(c) for c in vec];install(lab.TOOLS);rows=[]
    for c,(expected,baseline) in zip(vec,old):
        actual,candidate=bench(c);assert json.dumps(expected,sort_keys=True)==json.dumps(actual,sort_keys=True),(c['name'],c['case'])
        rows.append({'tool':c['name'],'case':c['case'],'baseline':baseline,'candidate':candidate,'equivalent':True})
    p=Path(output);p.write_text(json.dumps({'scope':'CPython native; synthetic examples; not a hard timeout, not isolate telemetry; schema_boundary representative not exhaustive','rows':rows},indent=2));flat=[{'tool':r['tool'],'case':r['case'],'equivalent':r['equivalent'],**{f'{v}_{k}':value for v in ('baseline','candidate') for k,value in r[v].items()}} for r in rows]
    with p.with_suffix('.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=flat[0]);w.writeheader();w.writerows(flat)
    print(f'{len(rows)} native differential cases; 20 repeats per case per configuration; exact results equal')
if __name__=='__main__':main(sys.argv[1])
