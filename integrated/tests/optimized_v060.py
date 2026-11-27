"""Exact candidate optimizations, preserving the baseline registry and input schemas.
Only two fixed pure functions are replaced after differential tests; all other
algorithms and JSON validation remain in the original lab module.
"""
import ast, statistics

def code(source):
    try: tree=ast.parse(source)
    except (SyntaxError,ValueError,RecursionError):raise ValueError('invalid_python_syntax') from None
    nodes=funcs=branches=0;imports=set()
    function_types=(ast.FunctionDef,ast.AsyncFunctionDef)
    branch_types=(ast.If,ast.For,ast.AsyncFor,ast.While,ast.IfExp,ast.ExceptHandler,ast.comprehension,ast.Match)
    for node in ast.walk(tree):
        nodes+=1
        funcs+=isinstance(node,function_types)
        branches+=isinstance(node,branch_types)
        if isinstance(node,ast.ImportFrom) and node.module:imports.add(node.module.split('.')[0])
        elif isinstance(node,ast.Import):imports.update(a.name.split('.')[0] for a in node.names)
    return {'syntax_valid':True,'nodes':nodes,'functions':funcs,'branch_nodes':branches,'import_roots':sorted(imports),'scope':'python_ast_only_not_execution_or_full_complexity'}

def series(values,window):
    window=int(window)
    if window>len(values):raise ValueError('window_exceeds_series')
    # Python statistics.mean preserves exact integer sums; use a rolling integer
    # sum only for homogeneous integers. Float/mixed input keeps original logic.
    if all(type(x) is int for x in values):
        total=sum(values[:window]);averages=[]
        for i in range(window,len(values)+1):
            if i>window:total+=values[i-1]-values[i-window-1]
            averages.append(total//window if total%window==0 else total/window)
    else: averages=[statistics.mean(values[i-window:i]) for i in range(window,len(values)+1)]
    return {'moving_average':averages,'changes':[b-a for a,b in zip(values,values[1:])],'window':window}

def install(registry):
    for name,fn in [('code_structure_analyze',code),('time_series_analyze',series)]:
        spec,_=registry[name];registry[name]=(spec,fn)
