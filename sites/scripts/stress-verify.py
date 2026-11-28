"""Verify the original 23x10 stress vectors against independent expected results."""
import collections
import csv
import hashlib
import json
from pathlib import Path
import sys
from uuid import UUID
from vectors import assert_equal

vectors = {x['id']: x for x in json.loads(Path(sys.argv[1]).read_text())}
raw = json.loads(Path(sys.argv[2]).read_text())['rows']
assert len(vectors) == len(raw) == 230
assert {r['id'] for r in raw} == vectors.keys()
counts = collections.Counter(v['tool'] for v in vectors.values())
assert len(counts) == 23 and set(counts.values()) == {10}
seen = set()
results = []
for row in raw:
    case = vectors[row['id']]
    assert row['status'] == 200 and case['case'] == 'stress'
    assert hashlib.sha256(row['wire'].encode()).hexdigest() == row['response_sha256']
    result = json.loads(row['wire'])['result']
    assert result['isError'] is False
    actual = result['structuredContent']
    assert actual == json.loads(result['content'][0]['text'])
    request_id = actual.pop('request_id')
    assert UUID(request_id).version == 4 and request_id not in seen
    seen.add(request_id)
    expected = case['expected']
    if type(expected.get('result')) is int and abs(expected['result']) > 2**53-1:
        assert actual.pop('exact_integer') == str(expected['result'])
    assert_equal(actual, expected)
    results.append(dict(id=row['id'], tool=case['tool'], status='PASS', request_id=request_id,
                        client_ms=row['client_ms'], response_sha256=row['response_sha256'], oracle=case['oracle']))
with Path(sys.argv[3]).open('w', encoding='utf-8', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=results[0])
    writer.writeheader()
    writer.writerows(results)
print(f'{len(results)}/230 original stress calls passed, {len(seen)} unique IDs')
