#!/usr/bin/env python3
"""Validate an acceptance ledger. Does not independently authenticate evidence."""
import json
import sys


def validate(data):
    if not isinstance(data, dict):
        return ['ledger must be an object']
    errors = []
    status = data.get('status')
    if status not in ('VERIFIED', 'PARTIAL', 'BLOCKED', 'FAILED'):
        errors.append('invalid overall status')
    criteria = data.get('criteria')
    if not isinstance(criteria, list) or not criteria:
        return errors + ['criteria must be a nonempty list']
    ids = set()
    states = []
    for i, criterion in enumerate(criteria):
        if not isinstance(criterion, dict):
            errors.append(f'criterion {i}: expected object')
            continue
        cid = criterion.get('id')
        if not isinstance(cid, str) or not cid.strip() or cid in ids:
            errors.append(f'criterion {i}: missing or duplicate id')
        else:
            ids.add(cid)
        state = criterion.get('state')
        states.append(state)
        if state not in ('PASS', 'FAIL', 'BLOCKED', 'UNVERIFIED'):
            errors.append(f'criterion {i}: invalid state')
        key = 'evidence' if state == 'PASS' else 'reason'
        val = criterion.get(key)
        if not isinstance(val, str) or not val.strip():
            errors.append(f'criterion {i}: missing {key}')
    if status == 'VERIFIED' and any(s != 'PASS' for s in states):
        errors.append('VERIFIED requires all criteria PASS')
    if status != 'VERIFIED' and states and all(s == 'PASS' for s in states):
        errors.append('non-VERIFIED status requires an outstanding criterion')
    if status == 'BLOCKED' and 'BLOCKED' not in states:
        errors.append('BLOCKED requires a blocked criterion')
    if status == 'FAILED' and 'FAIL' not in states:
        errors.append('FAILED requires a failed criterion')
    return errors


def main():
    if len(sys.argv) != 2:
        print('Usage: python verify.py ledger.json', file=sys.stderr)
        return 2
    try:
        with open(sys.argv[1], encoding='utf-8') as f:
            errors = validate(json.load(f))
    except (OSError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 2
    print(json.dumps({'valid': not errors, 'errors': errors}, ensure_ascii=False))
    return int(bool(errors))


if __name__ == '__main__':
    sys.exit(main())
