"""Build the bounded read-only Python guest filesystem image."""
import importlib.util
import marshal
from pathlib import Path
import sys
import zipfile

# List established by import tracing and correlated against all-tool tests.
MODULES = """
__future__ _collections_abc _compression _weakrefset abc ast base64 bisect bz2
codecs collections collections.abc contextlib copy copyreg decimal enum fnmatch
fractions functools genericpath glob hashlib importlib importlib._abc
importlib._bootstrap importlib._bootstrap_external importlib.util io json
json.decoder json.encoder json.scanner keyword linecache locale lzma ntpath
numbers operator os pathlib pathlib._abc pathlib._local posixpath random re
re._casefix re._compiler re._constants re._parser reprlib shutil stat statistics
string struct threading token tokenize traceback types warnings weakref zipfile
zipfile._path zipfile._path.glob
""".split()

def image(stdlib, root, output):
    if sys.version_info[:2] != (3, 13):
        raise RuntimeError('Build the guest image with CPython 3.13')
    sources = {}
    for name in MODULES:
        part = Path(*name.split('.'))
        path = part.with_suffix('.py')
        if not (stdlib / path).is_file():
            path = part / '__init__.py'
        sources[path.as_posix()] = stdlib / path
    for name in ('__init__', 'aliases', 'ascii', 'latin_1', 'utf_8', 'cp437'):
        path = f'encodings/{name}.py'
        sources[path] = stdlib / path
    for path in root.joinpath('runtime').glob('*.py'):
        sources[path.name] = path
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, path in sorted(sources.items()):
            if not path.is_file():
                if name == 'collections/abc/__init__.py':
                    # Some WASI distributions omit aliases which are frozen in the guest.
                    continue
                raise FileNotFoundError(path)
            code = compile(path.read_bytes(), '/lab/' + name, 'exec', dont_inherit=True)
            info = zipfile.ZipInfo(name + 'c', (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, importlib.util.MAGIC_NUMBER + b'\0' * 12 + marshal.dumps(code))

if __name__ == '__main__':
    image(Path(sys.argv[1]), Path(__file__).resolve().parents[1], Path(sys.argv[2]))
