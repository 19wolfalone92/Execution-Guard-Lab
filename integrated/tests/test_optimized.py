import json, random
import pytest
from lab import TOOLS
from integrated.core.src.optimized import code,series

def exact(a,b):
    assert json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)
@pytest.mark.parametrize('source',['','x=1\n'*4000,'import a.b, c\nfrom .d.e import f\n','async def f():\n async for x in y:\n  if x: return x\n','match x:\n case 1: pass\n','x=[a for a in b if a]\ntry: pass\nexcept Exception: pass\n'])
def test_ast(source):exact(TOOLS['code_structure_analyze'][1](source=source),code(source))
def test_invalid_ast():
    for fn in (TOOLS['code_structure_analyze'][1],code):
        with pytest.raises(ValueError,match='invalid_python_syntax'):fn(source='def :')
@pytest.mark.parametrize('kind',['int','float','mixed'])
def test_series(kind):
    rng=random.Random(408)
    for _ in range(120):
        vals=[rng.randrange(-10**12,10**12) for _ in range(rng.randint(1,256))]
        if kind!='int':vals=[v/7 if kind=='float' or i%2 else v for i,v in enumerate(vals)]
        w=rng.randint(1,len(vals));exact(TOOLS['time_series_analyze'][1](values=vals,window=w),series(vals,w))
