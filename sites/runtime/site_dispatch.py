"""Validate and call only the existing, fixed Python registry."""
import io
import json
import sys
import tokenize

from lab import TOOLS, call, decode
from optimized import install

install(TOOLS)
sys.setrecursionlimit(280)
MAX_RESULT = 128 * 1024
MAX_LINES = 800_000
KNOWN_ERRORS = frozenset("""
ast_complexity_limit computation_limit constant_predictor constant_series
data_depth_limit division_by_zero duplicate_dependency duplicate_identifier
duplicate_json_key invalid_arguments invalid_base64 invalid_internal_output
invalid_python_syntax invalid_unicode length_mismatch nonfinite_number
request_too_large result_too_large unknown_tool window_exceeds_series
""".split())

def bounded_source(source):
    """Cap parser nesting before parsing. Source stays inert throughout."""
    depth = consecutive = 0
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.OP:
                if token.string in ('(', '[', '{'):
                    depth += 1
                elif token.string in (')', ']', '}'):
                    depth -= 1
                consecutive += 1
                if depth > 80 or consecutive > 100:
                    raise ValueError('ast_complexity_limit')
            elif token.type not in (tokenize.NL, tokenize.COMMENT):
                consecutive = 0
    except (tokenize.TokenError, SyntaxError):
        raise ValueError('invalid_python_syntax') from None

def compute(raw):
    params = decode(raw)['params']
    name = params['name']
    args = params.get('arguments', {})
    if name == 'code_structure_analyze' and isinstance(args, dict):
        src = args.get('source')
        if isinstance(src, str) and len(src) <= 16_000:
            bounded_source(src)
    return call(name, args)

def dispatch(raw):
    remaining = MAX_LINES

    def trace(frame, event, arg):
        nonlocal remaining
        if event == 'line':
            remaining -= 1
            if remaining <= 0:
                raise ValueError('computation_limit')
        return trace

    try:
        sys.settrace(trace)
        result = compute(raw)
        sys.settrace(None)
        number = result.get('result')
        if type(number) is int and abs(number) > 2**53 - 1:
            result['exact_integer'] = str(number)
        wire = json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode()
        if len(wire) > MAX_RESULT:
            raise ValueError('result_too_large')
        return b'+' + wire
    except (ArithmeticError, RecursionError, MemoryError):
        return b'-computation_limit'
    except (ValueError, SyntaxError, TypeError, KeyError) as exc:
        reason = str(exc)
        return b'-' + (reason if reason in KNOWN_ERRORS else 'invalid_arguments').encode('ascii')
    finally:
        sys.settrace(None)
