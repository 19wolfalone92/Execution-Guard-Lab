"""Native function CPU breakdown, not a Cloudflare isolate measurement."""
import ast,json,statistics,sys,time,tracemalloc
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from lab import TOOLS,call
from jsonschema import Draft202012Validator
from integrated.core.src.optimized import code
from integrated.tests.optimized_v060 import code as previous

def measure(fn):
    fn(); values=[]
    for _ in range(30):
        t=time.process_time_ns();fn();values.append((time.process_time_ns()-t)/1e6)
    tracemalloc.start();fn();_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    s=sorted(values);return dict(p50_cpu_ms=statistics.median(s),p95_cpu_ms=s[28],p99_cpu_ms=s[-1],max_cpu_ms=s[-1],python_alloc_peak_bytes=peak)
rows=[]
for label,source in [('typical','import math\ndef f(x): return x+1\n'),('dense_max','x=1\n'*4000),('functions','\n'.join(f'def f{i}(): return {i}' for i in range(500)))]:
    args={'source':source};spec,original=TOOLS['code_structure_analyze'];a=original(source);assert a==previous(source)==code(source)
    tree=ast.parse(source)
    phases={'parse':lambda:ast.parse(source),'walk':lambda:sum(1 for _ in ast.walk(tree)), 'input_schema':lambda:Draft202012Validator(spec['inputSchema']).is_valid(args),'output_schema':lambda:Draft202012Validator(spec['outputSchema']).is_valid(a),'serialize':lambda:json.dumps(a,allow_nan=False),'v060':lambda:previous(source),'v070':lambda:code(source),'baseline':lambda:original(source)}
    rows.append({'case':label,'source_chars':len(source),'nodes':a['nodes'],'equivalent':True,'phases':{n:measure(f) for n,f in phases.items()}})
Path(sys.argv[1]).write_text(json.dumps({'scope':'native CPython process CPU; standalone phases overlap and are not additive; no gateway or cloud isolate CPU','rows':rows},indent=2));print(json.dumps(rows))
