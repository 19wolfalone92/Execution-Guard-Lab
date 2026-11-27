"""No-network tests of the exact one-shot diagnostic and cleanup control flow."""
import datetime as dt
import json
import os
import uuid
from unittest.mock import patch
import unittest
from cloud_runtime import write_probe as probe

ACCOUNT = "a" * 32
TOKEN_ID = "1" * 32
VERSION = str(uuid.UUID(int=1))
DEPLOYMENT = str(uuid.UUID(int=3))

class Reply:
    def __init__(self, body, status=200):
        self.body = body
        self.status = status
        self.headers = {}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, n): return self.body[:n]

class Fake:
    def __init__(self, extra=False, paid=False, broad=False, unknown_plan=False, free_plan=False):
        self.extra = extra
        self.paid = paid
        self.broad = broad
        self.unknown_plan = unknown_plan
        self.free_plan = free_plan
        self.writes = []
        self.enabled = False
        self.uploaded = False
        self.deleted = False
        self.worker_present = False
        self.diagnostic_calls = 0
        self.request = None
    def open(self, req, timeout):
        url = req.full_url
        method = req.get_method()
        path = url.split("/client/v4")[-1]
        if "workers.dev/health" in url:
            self.diagnostic_calls += 1
            self.request = req
            return Reply(b"eglab-static-v1")
        if method != "GET":
            self.writes.append((method, path))
        if path.endswith("/tokens/verify") or path == "/user/tokens/verify":
            result = {"id": TOKEN_ID, "status": "active",
                      "expires_on": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat()}
        elif path == "/user/tokens/" + TOKEN_ID:
            resource = "com.cloudflare.api.account.*" if self.broad else "com.cloudflare.api.account." + ACCOUNT
            result = {"policies": [{"effect": "allow", "permission_groups": [{"name": "Workers Scripts Write"}],
                                    "resources": {resource: "*"}}]}
        elif path == "/accounts/" + ACCOUNT:
            result = {"id": ACCOUNT}
        elif path == "/accounts?per_page=50":
            result = [{"id": ACCOUNT}] + ([{"id": "b" * 32}] if self.extra else [])
            info = {"total_count": len(result), "total_pages": 1}
        elif path == "/accounts/" + ACCOUNT + "/subscriptions":
            if self.paid:
                result = [{"price": 5, "rate_plan": {"id": "workers_paid"}}]
            elif self.unknown_plan:
                result = [{"price": 0, "rate_plan": {"id": "workers"}}]
            elif self.free_plan:
                result = [{"price": 0, "rate_plan": {"id": "free"}}]
            else:
                result = []
        elif path.endswith("/workers/scripts"):
            result = ([{"id": "eglab-probe-123-1"}] if self.worker_present else [])
        elif path.endswith("/workers/subdomain"):
            result = {"subdomain": "synthetic-lab"}
        elif path.endswith("/subdomain") and method == "GET":
            result = {"enabled": self.enabled, "previews_enabled": False}
        elif path.endswith("/deployments") and method == "GET":
            result = {"deployments": [{"id": DEPLOYMENT,
                        "versions": [{"version_id": VERSION, "percentage": 100}]}]}
        elif method == "POST" and path.endswith("/subdomain"):
            self.enabled = json.loads(req.data)["enabled"]
            result = {"enabled": self.enabled, "previews_enabled": False}
        elif method == "PUT" and "/workers/scripts/eglab-probe-" in path:
            self.uploaded = True
            self.worker_present = True
            result = {"id": "synthetic"}
        elif method == "DELETE" and "/workers/scripts/eglab-probe-" in path:
            self.deleted = True
            self.worker_present = False
            result = {"id": "synthetic"}
        else:
            raise AssertionError("unexpected mock path: " + path)
        body = {"success": True, "result": result}
        if "info" in locals(): body["result_info"] = info
        return Reply(json.dumps(body).encode())


def run(fake, allow_stop=False):
    env = {
        "CF_TOKEN": "synthetic-token", "CF_ACCOUNT": ACCOUNT,
        "GITHUB_REPOSITORY": "19wolfalone92/Execution-Guard-Lab",
        "GITHUB_REF": "refs/heads/qualification/cloud-runtime-oauth-20261127",
        "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "c" * 40,
    }
    with patch.dict(os.environ, env), patch.object(probe, "opener", fake), patch.object(probe, "report", {
        "steps": [], "status": "PARTIAL", "diagnostic_request_count": 0,
    }) as result:
        try:
            probe.main()
        except probe.Stop:
            if not allow_stop: raise
        return result


class WriteProbeTests(unittest.TestCase):
    def test_single_diagnostic_happy_path_and_cleanup(self):
        fake = Fake()
        result = run(fake)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["diagnostic_request_count"], 1)
        self.assertEqual(fake.diagnostic_calls, 1)
        self.assertEqual(fake.request.get_header("User-agent"), "ExecutionGuardLab/0.9.0")
        self.assertTrue(fake.deleted and not fake.worker_present and not fake.enabled)
        self.assertEqual(result["cleanup_status"], "PASS")
        self.assertEqual(len(fake.writes), 4)
        serialized = json.dumps(result)
        self.assertNotIn("synthetic-token", serialized)
        self.assertNotIn(ACCOUNT, serialized)

    def test_ambiguous_upload_is_read_back_and_cleaned(self):
        import urllib.error
        class LostUploadReply(Fake):
            def open(self, req, timeout):
                if req.get_method() == "PUT" and "/workers/scripts/eglab-probe-" in req.full_url:
                    self.writes.append((req.get_method(), req.full_url.split("/client/v4")[-1]))
                    self.uploaded = True
                    self.worker_present = True
                    raise urllib.error.URLError("synthetic lost response")
                return super().open(req, timeout)
        fake = LostUploadReply()
        result = run(fake, allow_stop=True)
        self.assertTrue(fake.deleted and not fake.worker_present and not fake.enabled)
        self.assertEqual(fake.diagnostic_calls, 0)
        self.assertEqual(result["cleanup_status"], "PASS")
        self.assertNotIn("synthetic lost response", json.dumps(result))
        self.assertNotIn("synthetic-token", json.dumps(result))

    def test_extra_visible_account_fails_before_mutation(self):
        fake = Fake(extra=True)
        with self.assertRaisesRegex(probe.Stop, "account_isolation_read_guard_failed"):
            run(fake)
        self.assertEqual(fake.writes, [])
        self.assertEqual(fake.diagnostic_calls, 0)

    def test_paid_subscription_fails_before_mutation(self):
        fake = Fake(paid=True)
        with self.assertRaisesRegex(probe.Stop, "paid_or_unverified_cloudflare_subscription"):
            run(fake)
        self.assertEqual(fake.writes, [])
        self.assertEqual(fake.diagnostic_calls, 0)



    def test_unknown_subscription_fails_closed_before_mutation(self):
        fake = Fake(unknown_plan=True)
        with self.assertRaisesRegex(probe.Stop, "paid_or_unverified_cloudflare_subscription"):
            run(fake)
        self.assertEqual(fake.writes, [])
        self.assertEqual(fake.diagnostic_calls, 0)

    def test_explicit_free_subscription_allows_guard(self):
        fake = Fake(free_plan=True)
        result = run(fake)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(fake.diagnostic_calls, 1)
        self.assertTrue(fake.deleted and not fake.enabled)

    def test_billing_read_unavailable_fails_before_mutation(self):
        import io
        import urllib.error
        class BillingDenied(Fake):
            def open(self, req, timeout):
                if req.full_url.endswith("/subscriptions"):
                    raise urllib.error.HTTPError(req.full_url, 403, "billing read denied", {}, io.BytesIO(b"denied"))
                return super().open(req, timeout)
        fake = BillingDenied()
        with self.assertRaisesRegex(probe.Stop, "cloudflare_api_rejected_account_subscriptions_read"):
            run(fake)
        self.assertEqual(fake.writes, [])
        self.assertEqual(fake.diagnostic_calls, 0)

    def test_broad_write_scope_fails_before_mutation(self):
        fake = Fake(broad=True)
        with self.assertRaisesRegex(probe.Stop, "worker_write_scope_not_exact_account"):
            run(fake)
        self.assertEqual(fake.writes, [])
        self.assertEqual(fake.diagnostic_calls, 0)

    def test_denial_stops_after_one_http_request_and_cleans_up(self):
        import io
        import urllib.error
        class Denied(Fake):
            def open(self, req, timeout):
                if "workers.dev/health" in req.full_url:
                    self.diagnostic_calls += 1
                    self.request = req
                    raise urllib.error.HTTPError(req.full_url, 403, "denied", {}, io.BytesIO(b"sensitive-body"))
                return super().open(req, timeout)
        fake = Denied()
        result = run(fake, allow_stop=True)
        self.assertEqual(fake.diagnostic_calls, 1)
        self.assertEqual(result["diagnostic_request_count"], 1)
        self.assertTrue(fake.deleted and not fake.enabled)
        rows = {row["step"]: row for row in result["steps"]}
        evidence = rows["https_single_attempt"]
        self.assertEqual(evidence["http_status"], 403)
        self.assertEqual(evidence["status"], "BLOCKED")
        self.assertEqual(rows["cleanup_delete_worker"]["status"], "PASS")
        self.assertNotIn("sensitive-body", json.dumps(result))
        self.assertEqual(fake.request.get_header("User-agent"), "ExecutionGuardLab/0.9.0")
