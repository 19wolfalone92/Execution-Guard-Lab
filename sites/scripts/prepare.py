"""Build the pinned, bounded CPython reactor on Linux x86_64."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache'

def get(item):
    name, (url, digest) = item
    filename = CACHE / f'{name}-{digest[:12]}.archive'
    if not filename.exists():
        with tempfile.NamedTemporaryFile(dir=CACHE, delete=False) as temporary:
            temp = Path(temporary.name)
            try:
                with urllib.request.urlopen(url, timeout=120) as response:
                    shutil.copyfileobj(response, temporary)
                temporary.flush()
                with temp.open('rb') as f:
                    if hashlib.file_digest(f, 'sha256').hexdigest() != digest:
                        raise RuntimeError(f'{name}: checksum mismatch')
                temp.rename(filename)
            finally:
                temp.unlink(missing_ok=True)
    with filename.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != digest:
            raise RuntimeError(f'{name}: corrupt cached archive')
    path = CACHE / f'{name}-{digest[:12]}'
    if not path.exists():
        with tempfile.TemporaryDirectory(dir=CACHE) as extracted:
            dest = Path(extracted) / 'input'
            if name == 'python_build':
                members = ('pyconfig.h', 'libpython3.13.a', 'Modules/_decimal/libmpdec/libmpdec.a',
                           'Modules/_hacl/libHacl_Hash_SHA2.a', 'Modules/expat/libexpat.a')
                with zipfile.ZipFile(filename) as z:
                    z.extractall(dest, members=members)
            else:
                with tarfile.open(filename) as t:
                    t.extractall(dest, filter='data')
            dest.rename(path)
    return name, path if name == 'python_build' else next(p for p in path.iterdir() if p.is_dir())

def main():
    CACHE.mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        paths = dict(pool.map(get, json.loads((ROOT / 'runtime/deps.json').read_text()).items()))
    if sys.version_info[:2] != (3, 13):
        raise RuntimeError("Build with CPython 3.13")
    subprocess.run(['bash', ROOT / 'scripts/link-reactor.sh', paths['sdk'], paths['cpython'],
                    paths['python_build'], paths['zlib'], ROOT / 'worker/kernel.wasm'], check=True)
    subprocess.run([sys.executable, ROOT / 'scripts/stdlib.py', paths['cpython'] / 'Lib',
                    ROOT / 'worker/stdlib.zip'], check=True)
    notices = ROOT / 'worker/THIRD_PARTY_NOTICES.txt'
    notices.write_text((paths['cpython'] / 'LICENSE').read_text() + '\n\n'
                       + (paths['zlib'] / 'LICENSE').read_text())
if __name__ == '__main__':
    if '--fetch-only' in sys.argv:
        CACHE.mkdir(exist_ok=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for name, path in pool.map(get, json.loads((ROOT / 'runtime/deps.json').read_text()).items()):
                print(name,path,flush=True)
    else:
        main()
