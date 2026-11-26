"""Fail-closed version floor for the isolated Lab. Not a complete vulnerability audit."""
import importlib.metadata as md
import sys
from pathlib import Path

HERE=Path(__file__).parent

def verify_runtime():
    errors=[]
    for line in (HERE/'requirements-runtime.txt').read_text(encoding='utf-8').splitlines():
        name,expected=line.split('==',1)
        try:actual=md.version(name)
        except md.PackageNotFoundError:actual='NOT_INSTALLED'
        if actual!=expected:errors.append(f'{name}: required={expected}; actual={actual}')
    return errors

def require_runtime():
    errors=verify_runtime()
    if errors:raise SystemExit('PRODUCTION START BLOCKED: unqualified dependency versions\n'+'\n'.join(errors))

if __name__=='__main__':
    require_runtime()
    print('Exact runtime version pins match; separate SDK, dependency audit and remote qualification still required.')
