"""Pure, bounded functions. No remote I/O, execution of input, or persistence."""
import ast, base64, binascii, hashlib, io, statistics, zipfile, stat, zlib

def install(register,obj,arr,string,enum,KEY,HEX):
    T={'type':'string'}; B={'type':'boolean'}; N={'type':'integer','minimum':0}; F={'type':'number'}
    V={'type':'number','minimum':-1e12,'maximum':1e12}
    ID=string(64,KEY)
    def vector(lo=1,hi=256):return {**arr(V,hi),'minItems':lo}
    def reg(n,d,i,o,f):register(n,d,i,f)['outputSchema']=o
    def math_calc(operation,a,b):
        if operation=='divide' and b==0:raise ValueError('division_by_zero')
        result={'add':lambda:a+b,'subtract':lambda:a-b,'multiply':lambda:a*b,'divide':lambda:a/b}[operation]()
        return {'result':result}
    reg('math_calculate','Four bounded arithmetic operations; no expressions or code.',obj(operation=enum('add','subtract','multiply','divide'),a=V,b=V),obj(result=F),math_calc)
    def stats(values):
        return {'count':len(values),'mean':statistics.mean(values),'median':statistics.median(values),'population_stddev':statistics.pstdev(values),'min':min(values),'max':max(values)}
    reg('statistics_analyze','Descriptive statistics of supplied finite sample.',obj(values=vector()),obj(count=N,mean=F,median=F,population_stddev=F,min=F,max=F),stats)
    def correlation(x,y):
        if len(x)!=len(y):raise ValueError('length_mismatch')
        if min(x)==max(x) or min(y)==max(y):raise ValueError('constant_series')
        return {'pearson_r':statistics.correlation(x,y),'count':len(x)}
    reg('correlation_analyze','Pearson correlation; no causal inference.',obj(x=vector(2),y=vector(2)),obj(pearson_r=F,count=N),correlation)
    def regression(x,y):
        if len(x)!=len(y):raise ValueError('length_mismatch')
        if min(x)==max(x):raise ValueError('constant_predictor')
        slope,intercept=statistics.linear_regression(x,y)
        r2=None if min(y)==max(y) else statistics.correlation(x,y)**2
        return {'slope':slope,'intercept':intercept,'r_squared':r2,'count':len(x)}
    reg('regression_analyze','Ordinary least squares with intercept; no forecast guarantee.',obj(x=vector(2),y=vector(2)),obj(slope=F,intercept=F,r_squared={'type':['number','null']},count=N),regression)
    def numerical(actual,expected,absolute_tolerance,relative_tolerance):
        delta=abs(actual-expected); limit=max(absolute_tolerance,relative_tolerance*max(abs(actual),abs(expected)))
        return {'matches':delta<=limit,'absolute_error':delta,'limit':limit}
    reg('numerical_compare','Symmetric absolute/relative tolerance comparison.',obj(actual=V,expected=V,absolute_tolerance={'type':'number','minimum':0,'maximum':1e12},relative_tolerance={'type':'number','minimum':0,'maximum':1}),obj(matches=B,absolute_error=F,limit=F),numerical)
    def series(values,window):
        window=int(window)
        if window>len(values):raise ValueError('window_exceeds_series')
        return {'moving_average':[statistics.mean(values[i-window:i]) for i in range(window,len(values)+1)],'changes':[b-a for a,b in zip(values,values[1:])],'window':window}
    reg('time_series_analyze','Trailing simple moving averages and successive differences, no look-ahead.',obj(values=vector(),window={'type':'integer','minimum':1,'maximum':256}),obj(moving_average=arr(F,256),changes=arr(F,256),window=N),series)
    def coverage(expected,observed):
        if len(set(expected))!=len(expected) or len(set(observed))!=len(observed):raise ValueError('duplicate_identifier')
        a,b=set(expected),set(observed)
        return {'missing':sorted(a-b),'unexpected':sorted(b-a),'matched':sorted(a&b),'complete':bool(a) and a==b,'scope':'supplied_identifiers_only'}
    reg('dataset_validate','Compare required and observed unique identifiers; no semantic verification.',obj(expected=arr(ID,256),observed=arr(ID,256)),obj(missing=arr(T,256),unexpected=arr(T,256),matched=arr(T,256),complete=B,scope=T),coverage)
    def completion(required,observed):
        if len(set(required))!=len(required) or len({x['id'] for x in observed})!=len(observed):raise ValueError('duplicate_identifier')
        by={x['id']:x['status'] for x in observed}; states={k:by.get(k,'UNVERIFIED') for k in required}
        return {'missing':sorted(set(required)-by.keys()),'unexpected':sorted(by.keys()-set(required)),'not_passed':sorted(k for k,v in states.items() if v!='PASS'),'declared_complete':bool(required) and all(v=='PASS' for v in states.values()) and not (by.keys()-set(required)),'scope':'supplied_statuses_not_independent_proof'}
    reg('completion_verify','Check completeness of required criteria against supplied statuses, not independent proof.',obj(required=arr(ID,128),observed=arr(obj(id=ID,status=enum('PASS','FAIL','BLOCKED','UNVERIFIED')),128)),obj(missing=arr(T,128),unexpected=arr(T,128),not_passed=arr(T,128),declared_complete=B,scope=T),completion)
    def regress(before,after):
        if len({r['id'] for r in before})!=len(before) or len({r['id'] for r in after})!=len(after):raise ValueError('duplicate_identifier')
        a={r['id']:r['status'] for r in before};b={r['id']:r['status'] for r in after}
        return {'regressed':sorted(k for k in a.keys()&b.keys() if a[k]=='PASS' and b[k]!='PASS'),'improved':sorted(k for k in a.keys()&b.keys() if a[k]!='PASS' and b[k]=='PASS'),'missing':sorted(a.keys()-b.keys()),'new':sorted(b.keys()-a.keys()),'scope':'supplied_test_statuses_only'}
    R=obj(id=ID,status=enum('PASS','FAIL','BLOCKED','UNVERIFIED','SKIP'))
    reg('regression_detect','Compare supplied baseline and candidate test statuses; missing is not pass.',obj(before=arr(R,128),after=arr(R,128)),obj(regressed=arr(T,128),improved=arr(T,128),missing=arr(T,128),new=arr(T,128),scope=T),regress)
    def code(source):
        try: tree=ast.parse(source)
        except (SyntaxError,ValueError,RecursionError):raise ValueError('invalid_python_syntax') from None
        nodes=list(ast.walk(tree)); funcs=sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) for n in nodes)
        branches=sum(isinstance(n,(ast.If,ast.For,ast.AsyncFor,ast.While,ast.IfExp,ast.ExceptHandler,ast.comprehension,ast.Match)) for n in nodes)
        imports=sorted({n.module.split('.')[0] for n in nodes if isinstance(n,ast.ImportFrom) and n.module}|{a.name.split('.')[0] for n in nodes if isinstance(n,ast.Import) for a in n.names})
        return {'syntax_valid':True,'nodes':len(nodes),'functions':funcs,'branch_nodes':branches,'import_roots':imports,'scope':'python_ast_only_not_execution_or_full_complexity'}
    reg('code_structure_analyze','Static Python syntax, function/branch counts and import roots. Never executes code.',obj(source=string(16000)),obj(syntax_valid=B,nodes=N,functions=N,branch_nodes=N,import_roots=arr(T,16000),scope=T),code)
    def artifact(data_base64,expected_sha256):
        data=decode_bytes(data_base64); actual=hashlib.sha256(data).hexdigest()
        return {'bytes':len(data),'sha256':actual,'matches':actual==expected_sha256,'scope':'supplied_bytes_only'}
    def decode_bytes(s):
        try:
            data=base64.b64decode(s,validate=True)
            if base64.b64encode(data).decode()!=s:raise ValueError('invalid_base64')
        except (binascii.Error,UnicodeError):raise ValueError('invalid_base64') from None
        return data
    reg('artifact_checksum','Compute and compare SHA-256 of provided base64 bytes, no filesystem access.',obj(data_base64=string(64000),expected_sha256=string(64,HEX)),obj(bytes=N,sha256=string(64,HEX),matches=B,scope=T),artifact)
    def archive(data_base64):
        data=decode_bytes(data_base64)
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                entries=z.infolist(); issues=set(); total=sum(i.file_size for i in entries)
                if len(entries)>128:issues.add('entry_limit')
                if total>1_000_000:issues.add('expanded_size_limit')
                seen=set()
                for i in entries:
                    p=i.orig_filename; parts=p.replace('\\','/').split('/'); norm='/'.join(x for x in parts if x not in ('','.')).casefold()
                    if not norm or p.startswith(('/','\\')) or '\\' in p or ':' in p or '\x00' in p or '..' in parts:issues.add('unsafe_path')
                    if norm in seen:issues.add('duplicate_path')
                    seen.add(norm)
                    mode=i.external_attr>>16
                    if stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR):issues.add('special_entry')
                    if i.flag_bits&1:issues.add('encrypted_entry')
                    if i.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):issues.add('unsupported_compression')
                    if i.file_size>200_000 or i.file_size>100*max(1,i.compress_size):issues.add('expansion_limit')
                if not issues:
                    # No extraction. Bound actual decompression; CRC verified on EOF.
                    for i in entries:
                        if i.is_dir():continue
                        with z.open(i) as f:
                            chunk=f.read(i.file_size+1)
                            if len(chunk)!=i.file_size or f.read(1):issues.add('size_mismatch')
                return {'valid':not issues,'entries':len(entries),'expanded_bytes':total,'issues':sorted(issues),'scope':'bounded_zip_structure_and_crc_not_malware_scan'}
        except (zipfile.BadZipFile,RuntimeError,NotImplementedError,EOFError,OSError,ValueError,zlib.error):return {'valid':False,'entries':0,'expanded_bytes':0,'issues':['invalid_zip'],'scope':'bounded_zip_structure_and_crc_not_malware_scan'}
    reg('archive_validate','Inspect bounded ZIP bytes in memory, reject unsafe paths and expansion, no extraction.',obj(data_base64=string(64000)),obj(valid=B,entries=N,expanded_bytes=N,issues=arr(T),scope=T),archive)
    def drawdown(equity):
        peak=equity[0]; maximum=0; peak_i=0; start=end=0
        for i,v in enumerate(equity):
            if v>peak:peak=v;peak_i=i
            d=(peak-v)/peak
            if d>maximum:maximum=d;start=peak_i;end=i
        return {'max_drawdown_fraction':maximum,'peak_index':start,'trough_index':end,'scope':'supplied_equity_curve_only'}
    reg('equity_drawdown_analyze','Peak-to-trough relative drawdown of positive supplied equity curve.',obj(equity={**vector(),'items':{'type':'number','exclusiveMinimum':0,'maximum':1e12}}),obj(max_drawdown_fraction=F,peak_index=N,trough_index=N,scope=T),drawdown)
    def exam(reference,predicted):
        if len(reference)!=len(predicted):raise ValueError('length_mismatch')
        correct=sum(a==b for a,b in zip(reference,predicted))
        return {'correct':correct,'total':len(reference),'accuracy':correct/len(reference),'mismatch_indices':[i for i,(a,b) in enumerate(zip(reference,predicted)) if a!=b],'scope':'exact_label_match_not_exam_independence'}
    labels={**arr(string(128),256),'minItems':1}
    reg('exam_results_compare','Exact label scoring against supplied reference answers, no claim of holdout independence.',obj(reference=labels,predicted=labels),obj(correct=N,total=N,accuracy=F,mismatch_indices=arr(N,256),scope=T),exam)
    def workflow_ready(steps):
        from lab import workflow
        graph=workflow([{'id':s['id'],'depends_on':s['depends_on']} for s in steps]); by={s['id']:s for s in steps}
        ready=[]; inconsistent=[]
        if graph['valid']:
            for k in graph['topological_order']:
                s=by[k]; ok=all(by[d]['status']=='PASS' for d in s['depends_on'])
                if s['status']=='PENDING' and ok:ready.append(k)
                if s['status'] in ('PASS','RUNNING') and not ok:inconsistent.append(k)
        return {'graph_valid':graph['valid'],'ready':ready if not inconsistent else [],'inconsistent':inconsistent,'scope':'supplied_graph_only_no_execution'}
    reg('workflow_readiness','Compute pending ready steps and detect inconsistent dependency states. Does not execute.',obj(steps=arr(obj(id=ID,depends_on=arr(ID,32),status=enum('PASS','FAIL','BLOCKED','PENDING','RUNNING')),32)),obj(graph_valid=B,ready=arr(T),inconsistent=arr(T),scope=T),workflow_ready)
