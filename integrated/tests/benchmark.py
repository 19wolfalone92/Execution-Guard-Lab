"""CPU timings of exact baseline functions vs candidate, native CPython only."""
import json,statistics,time,tracemalloc,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from lab import TOOLS
from integrated.core.src.optimized import code,series
from cloud_runtime.cases import cases

def measure(fn,args):
    values=[];result=fn(**args)
    for _ in range(30):
        t=time.process_time_ns();fn(**args);values.append((time.process_time_ns()-t)/1e6)
    tracemalloc.start();fn(**args);_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    return result,{'p50_cpu_ms':statistics.median(values),'p95_cpu_ms':sorted(values)[28],'max_cpu_ms':max(values),'python_alloc_peak_bytes':peak}
rows=[]
for c in cases():
    if c['case']!='stress' or c['name'] not in ('code_structure_analyze','time_series_analyze'):continue
    fn=code if c['name']=='code_structure_analyze' else series
    a,old=measure(TOOLS[c['name']][1],c['arguments']);b,new=measure(fn,c['arguments'])
    assert json.dumps(a,sort_keys=True)==json.dumps(b,sort_keys=True)
    rows.append({'tool':c['name'],'baseline':old,'candidate':new,'equivalent':True})
report={'scope':'native CPython process CPU and Python allocations, not cloud isolate','rows':rows};Path(sys.argv[1]).write_text(json.dumps(report,indent=2));print(json.dumps(report))
