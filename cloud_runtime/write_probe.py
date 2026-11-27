"""One-shot, account-bound HTTPS diagnostic using a temporary static Worker.

The only request to the temporary workers.dev endpoint is one GET. The Worker
has no bindings, secrets, production routes, or application data. All Cloudflare
writes are limited to this collision-checked Worker and are cleaned up in finally.
"""
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from diagnostics.http_evidence import MAX_BODY, USER_AGENT, inspect_response

class Stop(Exception):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

opener = urllib.request.build_opener(NoRedirect())
report = {
    "scope": "single isolated static Worker HTTPS diagnostic; not MCP or production",
    "status": "PARTIAL",
    "diagnostic_request_count": 0,
    "user_agent": USER_AGENT,
    "steps": [],
}


def record(label, **fields):
    row = {"step": label, **fields}
    report["steps"].append(row)
    print(json.dumps(row, sort_keys=True), flush=True)


def require(ok, label):
    if not ok:
        raise Stop(label)


def _resource_classes(policy, account):
    resources = policy.get("resources")
    if not isinstance(resources, dict) or not resources:
        return {"unrecognized"}
    kinds = set()
    for raw in resources:
        name = str(raw).lower()
        if name == "com.cloudflare.api.account." + account:
            kinds.add("target_account")
        elif name in {"com.cloudflare.api.account.*", "com.cloudflare.api.account", "*"}:
            kinds.add("broad_or_unspecified")
        elif re.fullmatch(r"com\.cloudflare\.api\.account\.[a-f0-9]{32}", name):
            kinds.add("different_account")
        else:
            kinds.add("unrecognized")
    return kinds


def _verify_token_policy(policy_payload, account):
    policies = policy_payload.get("policies") if isinstance(policy_payload, dict) else None
    if not isinstance(policies, list):
        return False, "token_policy_unavailable"
    write_names = {
        "workers scripts write", "workers scripts edit", "workers admin", "workers editor",
        "workers kv storage write", "workers kv storage edit", "d1 write", "d1 edit",
        "workers r2 storage write", "workers r2 storage edit", "workers ci write", "workers ci edit",
    }
    matching_worker_write = False
    for policy in policies:
        if not isinstance(policy, dict) or policy.get("effect") != "allow":
            continue
        groups = policy.get("permission_groups", [])
        names = {
            str(group.get("name", "")).strip().lower()
            for group in groups if isinstance(group, dict)
        }
        write = names & write_names
        if not write:
            continue
        if write != {"workers scripts write"}:
            return False, "token_has_broader_write_permissions"
        if _resource_classes(policy, account) != {"target_account"}:
            return False, "worker_write_scope_not_exact_account"
        matching_worker_write = True
    if not matching_worker_write:
        return False, "account_scoped_workers_scripts_write_missing"
    return True, "exact_account_scoped_workers_scripts_write"


def _has_paid_subscription(subscriptions):
    if not isinstance(subscriptions, list):
        return None
    paid_plan_ids = {"lite", "pro", "pro_plus", "business", "enterprise", "workers_paid", "standard"}
    free_plan_ids = {"free", "partners_free"}
    for subscription in subscriptions:
        if not isinstance(subscription, dict):
            return None
        plan = subscription.get("rate_plan") or {}
        plan_id = str(plan.get("id", subscription.get("rate_plan_id", ""))).lower()
        price = subscription.get("price")
        if plan_id in paid_plan_ids or (isinstance(price, (int, float)) and price > 0):
            return True
        if plan_id in free_plan_ids and (price is None or price == 0):
            continue
        # Unknown billing records are not evidence of a no-cost Free account.
        return None
    return False


def main():
    token = os.environ.get("CF_TOKEN", "").strip()
    account = os.environ.get("CF_ACCOUNT", "").strip().lower()
    run = os.environ.get("GITHUB_RUN_ID", "")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    require(bool(token) and bool(re.fullmatch(r"[0-9a-f]{32}", account)), "credentials_missing_or_invalid")
    require(
        os.environ.get("GITHUB_REPOSITORY") == "19wolfalone92/Execution-Guard-Lab"
        and os.environ.get("GITHUB_REF") == "refs/heads/qualification/cloud-runtime-oauth-20261127",
        "repository_or_ref_mismatch",
    )
    require(bool(re.fullmatch(r"\d{1,20}", run)) and attempt == "1", "run_id_invalid_or_diagnostic_rerun_forbidden")

    name = f"eglab-probe-{run}-{attempt}"
    report.update(worker=name, github_sha=os.environ.get("GITHUB_SHA"))
    prefix = "/accounts/" + account
    script = prefix + "/workers/scripts/" + name

    def api(label, path, method="GET", data=None, ctype="application/json"):
        allowed_read = (
            path.startswith(prefix + "/") or path == prefix
            or path in ("/accounts?per_page=50", "/user/tokens/verify")
            or bool(re.fullmatch(r"/user/tokens/[a-f0-9]{32}", path))
        )
        require(allowed_read, "out_of_scope_api_path")
        allowed_writes = {("PUT", script), ("POST", script + "/subdomain"), ("DELETE", script)}
        if method != "GET":
            require((method, path) in allowed_writes, "out_of_scope_write")
        headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = ctype
        if isinstance(data, dict):
            data = json.dumps(data).encode()
        request = urllib.request.Request(
            "https://api.cloudflare.com/client/v4" + path,
            data=data,
            headers=headers,
            method=method,
        )
        started = time.perf_counter_ns()
        request_id = uuid.uuid4().hex
        try:
            with opener.open(request, timeout=20) as response:
                status = response.status
                body = json.loads(response.read(2_000_001))
        except urllib.error.HTTPError as error:
            raw = b""
            try:
                raw = error.read(MAX_BODY + 1)
            except Exception:
                pass
            codes = []
            try:
                payload = json.loads(raw[:MAX_BODY])
                codes = [item["code"] for item in payload.get("errors", []) if isinstance(item.get("code"), int)][:8]
            except Exception:
                pass
            evidence = inspect_response(
                error.code, error.headers, raw, b"", request_id=request_id,
                utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                duration_ms=(time.perf_counter_ns() - started) / 1_000_000,
            )
            keep = (
                "category", "cf_ray", "cf_error_type", "cf_error_origin", "server_header",
                "server_class", "content_type", "cloudflare_error_code",
                "cloudflare_error_code_source", "indicator", "body_fragment",
                "body_bytes_sampled", "truncated", "retry_after_seconds", "stop_reason", "duration_ms",
            )
            safe = {key: evidence[key] for key in keep if key in evidence}
            record(label, status="FAIL", http=error.code, codes=codes, request_id=request_id, **safe)
            raise Stop("cloudflare_api_rejected_" + label) from None
        except Exception as error:
            record(
                label, status="UNVERIFIED", error=type(error).__name__, request_id=request_id,
                duration_ms=round((time.perf_counter_ns() - started) / 1_000_000, 3),
            )
            raise Stop("cloudflare_api_transport_" + label) from None
        require(isinstance(body, dict) and body.get("success") is True, "cloudflare_api_unsuccessful_" + label)
        record(label, status="PASS", http=status, request_id=request_id,
               duration_ms=round((time.perf_counter_ns() - started) / 1_000_000, 3))
        return body

    token_path = prefix + "/tokens/verify" if token.startswith("cfat_") else "/user/tokens/verify"
    verified = api("token_active", token_path)["result"]
    require(verified.get("status") == "active", "inactive_token")
    expires = dt.datetime.fromisoformat(verified["expires_on"].replace("Z", "+00:00"))
    require(0 < (expires - dt.datetime.now(dt.timezone.utc)).total_seconds() <= 31 * 86400, "token_expiry_not_bounded")
    token_id = verified.get("id")
    require(isinstance(token_id, str) and re.fullmatch(r"[a-fA-F0-9]{32}", token_id), "token_id_unavailable")
    policy_path = prefix + "/tokens/" + token_id if token.startswith("cfat_") else "/user/tokens/" + token_id
    policy_payload = api("token_policy_read", policy_path)["result"]
    policy_ok, policy_reason = _verify_token_policy(policy_payload, account)
    require(policy_ok, policy_reason)
    record("token_policy_guard", status="PASS", result=policy_reason)

    acct = api("account_match", prefix)["result"]
    require(str(acct.get("id", "")).lower() == account, "account_mismatch")
    accounts = api("single_visible_account", "/accounts?per_page=50")
    info = accounts.get("result_info", {})
    visible = accounts.get("result")
    require(
        isinstance(visible, list) and info.get("total_count") == 1 and info.get("total_pages") == 1
        and len(visible) == 1 and str(visible[0].get("id", "")).lower() == account,
        "account_isolation_read_guard_failed",
    )

    # Billing Read is required for this gate. If the current plan cannot be
    # independently checked, do not create a Worker or risk a billable action.
    subscriptions = api("account_subscriptions_read", prefix + "/subscriptions").get("result")
    paid = _has_paid_subscription(subscriptions)
    require(paid is False, "paid_or_unverified_cloudflare_subscription")
    record("billing_guard", status="PASS", subscription_count=len(subscriptions), paid_subscription_detected=False)
    record("account_guard", status="PASS", expiry_utc=expires.isoformat(), visible_accounts=1,
           policy_basis="active short-lived token; exact account-scoped Workers Scripts Write; no paid subscription detected")

    workers = api("existing_worker_list", prefix + "/workers/scripts")["result"]
    require(isinstance(workers, list) and all(isinstance(worker, dict) for worker in workers), "worker_list_invalid")
    require(not any(worker.get("id") == name or worker.get("name") == name for worker in workers), "worker_name_collision")
    sub = api("existing_account_subdomain", prefix + "/workers/subdomain")["result"].get("subdomain", "")
    require(bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", sub)), "no_existing_workers_dev_subdomain")
    url = f"https://{name}.{sub}.workers.dev/health"
    report["test_url"] = url

    marker = "eglab-static-v1"
    source = (
        'export default {fetch(request){const u=new URL(request.url);return request.method==="GET"&&u.pathname==="/health"?'
        + "new Response(" + json.dumps(marker)
        + ',{headers:{"Cache-Control":"no-store","Content-Type":"text/plain"}}):new Response("Not found",{status:404});}};\n'
    ).encode()
    boundary = "eglab" + secrets.token_hex(16)
    metadata = json.dumps({"main_module": "worker.mjs", "compatibility_date": "2026-11-26", "bindings": []}).encode()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\nContent-Type: application/json\r\n\r\n".encode()
        + metadata
        + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"worker.mjs\"; filename=\"worker.mjs\"\r\nContent-Type: application/javascript+module\r\n\r\n".encode()
        + source
        + f"\r\n--{boundary}--\r\n".encode()
    )

    upload_attempted = False
    subdomain_disabled_confirmed = False
    cleanup_failures = []
    try:
        upload_attempted = True
        api("upload_static_worker", script, "PUT", body, "multipart/form-data; boundary=" + boundary)
        report["created"] = True
        record("source_hash", sha256=hashlib.sha256(source).hexdigest())
        # PUT creates the new Worker version and its initial 100% deployment.
        # Read back the exact active version; do not assume upload success means active.
        active = api("verify_active_deployment", script + "/deployments")["result"]["deployments"]
        require(isinstance(active, list) and len(active) == 1, "deployment_not_single")
        versions = active[0].get("versions")
        require(isinstance(versions, list) and len(versions) == 1 and versions[0].get("percentage") == 100,
                "deployment_not_single_version")
        report["deployment_id"] = str(uuid.UUID(active[0]["id"]))
        report["version_id"] = str(uuid.UUID(versions[0]["version_id"]))
        record("active_version", status="PASS", deployment_id=report["deployment_id"], version_id=report["version_id"])

        state = api("enable_test_subdomain", script + "/subdomain", "POST", {
            "enabled": True, "previews_enabled": False,
        })["result"]
        require(state.get("enabled") is True and state.get("previews_enabled") is False, "test_subdomain_not_enabled_exactly")
        record("test_subdomain", status="PASS", previews_enabled=False)

        from diagnostics.http_evidence import one_shot
        report["diagnostic_request_count"] += 1
        require(report["diagnostic_request_count"] == 1, "diagnostic_request_count_guard")
        result = one_shot(url, marker.encode("ascii"), opener=opener, context={
            "worker_identifier": name,
            "deployment_id": report["deployment_id"],
            "version_id": report["version_id"],
            "source_sha": report.get("github_sha"),
        })
        record("https_single_attempt", **result)
        require(result.get("status") == "PASS", "https_diagnostic_not_pass")

        state = api("disable_test_subdomain", script + "/subdomain", "POST", {
            "enabled": False, "previews_enabled": False,
        })["result"]
        require(state.get("enabled") is False and state.get("previews_enabled") is False, "test_subdomain_disable_not_confirmed")
        readback = api("verify_subdomain_disabled", script + "/subdomain")["result"]
        require(readback.get("enabled") is False and readback.get("previews_enabled") is False,
                "test_subdomain_disable_readback_failed")
        subdomain_disabled_confirmed = True
        report["public_test_endpoint_disabled"] = True
        report["status"] = "PASS"
    finally:
        if upload_attempted:
            try:
                current = api("cleanup_find_worker", prefix + "/workers/scripts")["result"]
                require(isinstance(current, list), "cleanup_worker_list_invalid")
                exists = any(worker.get("id") == name or worker.get("name") == name for worker in current)
                if exists:
                    if not subdomain_disabled_confirmed:
                        state = api("cleanup_disable_subdomain", script + "/subdomain", "POST", {
                            "enabled": False, "previews_enabled": False,
                        })["result"]
                        require(state.get("enabled") is False and state.get("previews_enabled") is False,
                                "cleanup_disable_not_confirmed")
                        report["public_test_endpoint_disabled"] = True
                    api("cleanup_delete_worker", script, "DELETE")
                    remaining = api("cleanup_verify_worker_absent", prefix + "/workers/scripts")["result"]
                    require(isinstance(remaining, list) and not any(
                        worker.get("id") == name or worker.get("name") == name for worker in remaining
                    ), "cleanup_worker_still_present")
                    report["worker_deleted"] = True
                    record("cleanup_delete_worker", status="PASS")
                else:
                    report["worker_deleted"] = False
                    record("cleanup_worker_absent", status="PASS")
            except Exception as error:
                cleanup_failures.append("worker_cleanup")
                record("cleanup_worker", status="FAIL", error=type(error).__name__)
        report["cleanup_status"] = "PARTIAL" if cleanup_failures else ("PASS" if upload_attempted else "NOT_REQUIRED")
        if cleanup_failures:
            report["cleanup_failures"] = cleanup_failures
            if report.get("status") == "PASS":
                report["status"] = "PARTIAL"


def _write_evidence():
    report["completed_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    path = Path(os.environ.get("DIAGNOSTIC_EVIDENCE_PATH", "diagnostic-evidence.json"))
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"evidence_file": str(path), "status": report.get("status"),
                      "diagnostic_request_count": report.get("diagnostic_request_count"),
                      "cleanup_status": report.get("cleanup_status")}, sort_keys=True), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Stop as error:
        report["status"] = "BLOCKED" if "https_" not in str(error) else "FAIL"
        report["stop_reason"] = str(error)
        if report.get("diagnostic_request_count") == 1:
            rows = [row for row in report.get("steps", []) if row.get("step") == "https_single_attempt"]
            if rows and rows[-1].get("status") == "BLOCKED":
                report["status"] = "BLOCKED"
            elif rows:
                report["status"] = "FAIL"
    except Exception as error:
        report["status"] = "FAIL"
        report["stop_reason"] = type(error).__name__
    finally:
        _write_evidence()
    sys.exit(0 if report.get("status") == "PASS" and report.get("cleanup_status") == "PASS" else 1)
