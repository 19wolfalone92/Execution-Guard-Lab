"""Compare a local Workers runtime with unchanged CPython and historical fixtures."""
import argparse, concurrent.futures, json, os, resource, sys, time, urllib.request
from pathlib import Path
from cases import ROOT, cases, evaluate
sys.path.insert(0,str(ROOT))

def main():
    p=argparse.ArgumentParser(); p.add_argument('--url'); p.add_argument('--output',required=True); p.add_argument('--prepare',action='store_true'); a=p.parse_args()
    vectors=cases()
    if a.prepare:
        # Copy exact baseline sources, not alternative implementations.
        for filename in ('lab.py','extensions.py'):
            (ROOT/'cloud_runtime'/'src'/filename).write_bytes((ROOT/filename).read_bytes())
        (ROOT/'cloud_runtime'/'src'/'fixed_cases.py').write_text('CASES = '+repr(vectors)+'\n')
        return
    rows=[]; expected=[]
    for i,c in enumerate(vectors):
        t=time.process_time_ns(); result=evaluate(c); ms=(time.process_time_ns()-t)/1e6
        valid=(result.get('isError') is True) if c['case']=='negative' else (not result.get('isError') and (c['case']!='baseline' or result.get('structuredContent')==c['expected']))
        expected.append(result); rows.append({'index':i,'tool':c['name'],'case':c['case'],'native_cpu_ms':ms,'native_pass':valid,'request_bytes':len(json.dumps(c['arguments']).encode()),'native_result':result})
    if a.url:
        def request(i):
            t=time.perf_counter_ns()
            with urllib.request.urlopen(a.url.rstrip('/')+'/case/'+str(i),timeout=15) as r: data=json.load(r)
            return data,(time.perf_counter_ns()-t)/1e6
        for i,row in enumerate(rows):
            try:
                data,ms=request(i); row.update(worker_wall_ms=ms,worker_result=data['result'],worker_pass=data['result']==expected[i])
            except Exception as e: row.update(worker_pass=False,worker_error=type(e).__name__)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            parallel=list(pool.map(request,[0,3,6,9]))
        parallel_pass=all(d['result']==expected[i] for i,(d,_) in zip([0,3,6,9],parallel))
    else: parallel_pass=None
    passed=sum(r['native_pass'] for r in rows)
    report={'scope':'local workerd HTTP vs CPython' if a.url else 'native CPython only','cases':len(rows),'native_pass':passed,'worker_pass':sum(r.get('worker_pass',False) for r in rows) if a.url else None,'parallel_pass':parallel_pass,'native_process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'worker_cpu_ms':None,'worker_ram_bytes':None,'rows':rows}
    Path(a.output).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print({k:v for k,v in report.items() if k!='rows'})
    return 0 if passed==len(rows) and (not a.url or (report['worker_pass']==len(rows) and parallel_pass)) else 1
if __name__=='__main__': raise SystemExit(main())
