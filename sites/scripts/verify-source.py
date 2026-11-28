"""Verify adapter inputs and supported schemas against the canonical source."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator

SITE = Path(__file__).resolve().parents[1]
ROOT = SITE.parent
sys.path.insert(0, str(ROOT))
from cloud_runtime.cases import cases, evaluate
from lab import TOOLS

canonical = {
    'lab.py': ROOT / 'lab.py',
    'extensions.py': ROOT / 'extensions.py',
    'optimized.py': ROOT / 'integrated/core/src/optimized.py',
}
for name, original in canonical.items():
    assert (SITE / 'runtime' / name).read_bytes() == original.read_bytes(), name

catalog = json.loads((SITE / 'worker/catalog.json').read_text())
registry = json.loads((ROOT / 'TOOL_REGISTRY.json').read_text())['tools']
authored = json.loads((ROOT / 'MCP_SCHEMAS.json').read_text())['tools']
assert len(catalog) == 23
assert [row['name'] for row in catalog] == list(TOOLS)
for bundled, historical in zip(catalog, registry):
    assert bundled == {key:historical[key] for key in bundled}
    assert bundled == TOOLS[bundled['name']][0]
if isinstance(authored, dict):
    for row in catalog:
        other = authored[row['name']]
        assert row['inputSchema'] == other.get('inputSchema',other)
else:
    assert {row['name'] for row in authored} == set(TOOLS)
    for row, other in zip(catalog,authored):
        assert row['name'] == other['name'] and row['inputSchema'] == other['inputSchema']

spec = importlib.util.spec_from_file_location("site_schema", SITE / 'runtime/jsonschema.py')
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)

def variants(row):
    yield row
    yield None
    yield []
    yield {}
    yield {**row, '__unknown__': True}
    for k in row:
        yield {p:v for p,v in row.items() if p != k}
        for value in (None, 0, False, [], {}, '', '🐺' * 4097):
            yield {**row,k:value}

count = 0
for case in cases():
    if case['case'] == 'negative':
        continue
    contract = TOOLS[case['name']][0]
    for which, value in (('inputSchema',case['arguments']),
                         ('outputSchema',evaluate(case)['structuredContent'])):
        schema = contract[which]
        Draft202012Validator.check_schema(schema)
        native = Draft202012Validator(schema)
        guest.Draft202012Validator.check_schema(schema)
        wasm_compatible = guest.Draft202012Validator(schema)
        for v in variants(value):
            assert native.is_valid(v) == wasm_compatible.is_valid(v), (case['name'],which)
            count += 1
print(f'23 source and schema matches. {count} validation comparisons passed.')
