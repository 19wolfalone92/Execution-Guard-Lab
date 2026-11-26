"""Compare a local Workers runtime with unchanged CPython and historical fixtures."""
import argparse, concurrent.futures, json, os, resource, statistics, sys, time, urllib.request
from pathlib import Path
from cases import ROOT, cases, evaluate
sys.path.insert(0,str(ROOT))

def runtime_processes():
    """Coarse Linux process-level telemetry; NOT Cloudflare per-isolate billing CPU/RAM."""
    found={}
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal(): continue
        try:
            if (path/'comm').read_text().strip()!='workerd': continue
            parts=(path/'stat').read_text().rsplit(')',1)[1].split()
            mem={line.split(':',1)[0]:int(line.split()[1]) for line in (path/'status').read_text().splitlines() if line.startswith(('VmRSS:','VmHWM:'))}
            found[path.name]={'ticks':int(parts[11])+int(parts[12]),'rss_kib':mem.get('VmRSS'),'peak_rss_kib':mem.get('VmHWM')}
        except (OSError,ValueError,IndexError): continue
    return found

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
        # Repeat stress cases in batches to reduce the 10ms /proc tick quantization.
        for i,row in enumerate(rows):
            if row['case']!='stress': continue
            before=runtime_processes(); wall=[]; correct=True
            for _ in range(10):
                d,ms=request(i);wall.append(ms);correct &= d['result']==expected[i]
            after=runtime_processes()
            row['repeat_stress']={'count':10,'correct':correct,'wall_median_ms':statistics.median(wall),'wall_max_ms':max(wall),'process_cpu_mean_ms':None,'process_rss_kib':None,'process_peak_rss_kib':None}
            if before and set(before)==set(after):
                ticks=sum(after[p]['ticks']-before[p]['ticks'] for p in before)
                row['repeat_stress'].update(process_cpu_mean_ms=ticks*1000/os.sysconf('SC_CLK_TCK')/10,process_rss_kib=sum(x['rss_kib'] or 0 for x in after.values()),process_peak_rss_kib=sum(x['peak_rss_kib'] or 0 for x in after.values()))
            if not correct: row['worker_pass']=False
    else: parallel_pass=None
    passed=sum(r['native_pass'] for r in rows)
    report={'scope':'local workerd HTTP vs CPython' if a.url else 'native CPython only','cases':len(rows),'native_pass':passed,'worker_pass':sum(r.get('worker_pass',False) for r in rows) if a.url else None,'parallel_pass':parallel_pass,'native_process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'worker_cpu_ms':None,'worker_ram_bytes':None,'telemetry_caveat':'per-process Linux workerd CPU and RSS estimates only; no production isolate/billing measurements','rows':rows}
    Path(a.output).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print({k:v for k,v in report.items() if k!='rows'})
    return 0 if passed==len(rows) and (not a.url or (report['worker_pass']==len(rows) and parallel_pass)) else 1
if __name__=='__main__': raise SystemExit(main())
