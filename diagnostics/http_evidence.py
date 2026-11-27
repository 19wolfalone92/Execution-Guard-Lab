"""One-shot, fail-closed HTTPS evidence capture.

The caller supplies an already-authorized URL. Redirects are not followed.
No User-Agent override, alternate route, retry, raw body, cookie, token,
Authorization header, exception message, or redirect target is retained.
"""
from datetime import datetime, timezone
import re
import socket
import ssl
import time
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlsplit

MAX_BODY = 4096
MAX_TIMEOUT_SECONDS = 10
USER_AGENT = "ExecutionGuardLab/0.9.0"
_CF_ERROR_CODE = re.compile(rb"(?i)\b(?:cloudflare\s+)?error\s+([0-9]{4})\b")
_BIC_TEXT = re.compile(
    rb"(?i)the owner of this website has banned your access based on your browser.s signature"
)
_ACCESS_TEXT = re.compile(rb"(?i)cloudflare\s+access")
_SAFE_SERVER = re.compile(r"^[A-Za-z0-9._/-]{1,64}$")
_SAFE_WORKER = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_SAFE_SHA = re.compile(r"^[0-9a-f]{40}$")
_SAFE_RAY = re.compile(r"^[0-9a-fA-F]{16,32}(?:-[A-Z]{3})?$")
_SAFE_RETRY = re.compile(r"^[0-9]{1,6}$")
_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def classify(status):
    if status in (401, 403):
        return "authorization_denied"
    if 300 <= status < 400:
        return "redirect"
    if status == 429:
        return "rate_limited"
    if status >= 500:
        return "server_error"
    if status >= 400:
        return "client_error"
    return "unexpected_response"


def _header(headers, name):
    try:
        value = headers.get(name, "") if headers is not None else ""
    except Exception:
        return ""
    return value.strip() if isinstance(value, str) else ""


def _safe_context(context):
    """Retain only known, tightly validated deployment identifiers."""
    if not isinstance(context, dict):
        return {}
    result = {}
    worker = context.get("worker_identifier")
    if isinstance(worker, str) and _SAFE_WORKER.fullmatch(worker):
        result["worker_identifier"] = worker
    for key in ("deployment_id", "version_id"):
        value = context.get(key)
        if isinstance(value, str) and _UUID.fullmatch(value):
            result[key] = value.lower()
    source_sha = context.get("source_sha")
    if isinstance(source_sha, str) and _SAFE_SHA.fullmatch(source_sha):
        result["source_sha"] = source_sha
    return result


def _body_indicators(status, body, server_class):
    """Return allowlisted hints only; body text never establishes attribution."""
    sample = body[:MAX_BODY]
    result = {}
    match = _CF_ERROR_CODE.search(sample) if status == 403 else None
    if match:
        code = int(match.group(1))
        result["indicator"] = f"body_mentions_{code}"
        if server_class == "cloudflare" or b"cloudflare" in sample.lower():
            result["cloudflare_error_code"] = code
            result["cloudflare_error_code_source"] = "response_body_unverified"
            result["body_fragment"] = f"Cloudflare Error {code}"
        else:
            result["body_fragment"] = f"Response body mentions error code {code}"
    elif status in (401, 403) and _BIC_TEXT.search(sample):
        result["indicator"] = "body_mentions_browser_signature_denial"
        result["body_fragment"] = "Browser-signature denial text"
    elif status in (401, 403) and _ACCESS_TEXT.search(sample):
        result["indicator"] = "body_mentions_access"
        result["body_fragment"] = "Cloudflare Access text"
    return result


def inspect_response(
    status,
    headers,
    body,
    expected,
    *,
    context=None,
    request_id=None,
    utc=None,
    duration_ms=None,
):
    """Build a bounded, allowlisted evidence row; never return arbitrary body/header data."""
    result = {
        "source_attribution": "UNVERIFIED",
        "subsequent_operations": "STOP_UNLESS_EXPECTED",
        "http": status,
        "http_status": status,
        "category": classify(status),
        "body_bytes_sampled": len(body),
        "truncated": len(body) > MAX_BODY,
        "body_fragment": None,
        "retry_permitted": False,
        "stop_reason": f"http_{status}",
    }
    if request_id and re.fullmatch(r"[0-9a-f]{32}", request_id):
        result["request_id"] = request_id
        result["request_correlation_id"] = request_id
    if isinstance(utc, str) and utc:
        result["utc"] = utc
    if isinstance(duration_ms, (int, float)) and duration_ms >= 0:
        result["duration_ms"] = round(float(duration_ms), 3)
    result.update(_safe_context(context))

    ray = _header(headers, "CF-Ray")
    if _SAFE_RAY.fullmatch(ray):
        result["cf_ray"] = ray

    for header_name, evidence_name in (("CF-Error-Type", "cf_error_type"), ("CF-Error-Origin", "cf_error_origin")):
        value = _header(headers, header_name)
        if value and re.fullmatch(r"[A-Za-z0-9._/-]{1,64}", value):
            result[evidence_name] = value

    server = _header(headers, "Server")
    server_class = server.lower() if server.lower() in (
        "cloudflare", "nginx", "envoy", "github.com"
    ) else "other"
    if server and _SAFE_SERVER.fullmatch(server):
        result["server_header"] = server
    if server_class != "other":
        result["server_class"] = server_class

    content_type = _header(headers, "Content-Type").split(";", 1)[0].strip().lower()
    if content_type in ("text/plain", "text/html", "application/json"):
        result["content_type"] = content_type

    result.update(_body_indicators(status, body, server_class))

    retry = _header(headers, "Retry-After")
    if status == 429 and _SAFE_RETRY.fullmatch(retry):
        result["retry_after_seconds"] = int(retry)

    location = _header(headers, "Location")
    if location:
        try:
            parsed = urlsplit(location)
            result["redirect"] = {
                "present": True,
                "scheme": parsed.scheme if parsed.scheme in ("http", "https") else "other",
                "query_present": bool(parsed.query),
                "fragment_present": bool(parsed.fragment),
            }
        except ValueError:
            result["redirect"] = {"present": True, "malformed": True}

    if len(body) <= MAX_BODY and body == expected and status == 200:
        result.update(
            category="expected_response",
            body_fragment=expected.decode("ascii"),
            status="PASS",
            stop_reason="expected_static_marker",
            subsequent_operations="EXPECTED_RESPONSE_ONLY",
        )
    else:
        result["status"] = "BLOCKED" if status in (401, 403) else "FAIL"
        if status == 200:
            result["stop_reason"] = "unexpected_body"
        elif 300 <= status < 400:
            result["stop_reason"] = "redirect_not_followed"
    return result


def one_shot(url, expected, *, opener=None, context=None):
    """Perform exactly one GET to a preauthorized URL without changing its UA."""
    if not re.fullmatch(rb"eglab-static-v[12]", expected):
        raise ValueError("only static markers allowed")

    identifier = uuid.uuid4().hex
    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.monotonic_ns()
    base = {
        "utc": started_utc,
        "operation": "GET",
        "stage": "https_smoke",
        "request_id": identifier,
        "request_correlation_id": identifier,
        "user_agent": USER_AGENT,
        **_safe_context(context),
    }
    opener = opener or urllib.request.build_opener(NoRedirect())
    # Identify the actual application truthfully. This is the documented
    # Cloudflare workers.dev remedy for non-browser clients; never spoof a browser.
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Cache-Control": "no-cache",
            "X-Lab-Diagnostic-ID": identifier,
        },
    )
    try:
        with opener.open(req, timeout=MAX_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_BODY + 1)
            elapsed = (time.monotonic_ns() - started) / 1_000_000
            row = inspect_response(
                response.status,
                response.headers,
                body,
                expected,
                context=context,
                request_id=identifier,
                utc=started_utc,
                duration_ms=elapsed,
            )
    except urllib.error.HTTPError as error:
        try:
            body = error.read(MAX_BODY + 1)
        except Exception:
            body = b""
        elapsed = (time.monotonic_ns() - started) / 1_000_000
        row = inspect_response(
            error.code,
            error.headers,
            body,
            expected,
            context=context,
            request_id=identifier,
            utc=started_utc,
            duration_ms=elapsed,
        )
    except Exception as error:
        cause = error.reason if isinstance(error, urllib.error.URLError) else error
        category = (
            "tls_error" if isinstance(cause, ssl.SSLError)
            else "dns_error" if isinstance(cause, socket.gaierror)
            else "timeout" if isinstance(cause, TimeoutError)
            else "transport_error"
        )
        exception_type = type(cause).__name__
        if exception_type not in (
            "SSLError",
            "SSLCertVerificationError",
            "gaierror",
            "TimeoutError",
            "ConnectionError",
            "RemoteDisconnected",
            "ConnectionResetError",
            "ConnectionRefusedError",
        ):
            exception_type = "other"
        row = {
            "source_attribution": "UNVERIFIED",
            "subsequent_operations": "STOP_UNLESS_EXPECTED",
            "http": None,
            "http_status": None,
            "category": category,
            "status": "FAIL",
            "stop_reason": category,
            "exception_type": exception_type,
            "retry_permitted": False,
            "duration_ms": round((time.monotonic_ns() - started) / 1_000_000, 3),
        }
    return {**base, **row}
