"""Independent qualification with the current official MCP Python SDK 2.x.

The local-fixture mode creates an ephemeral RSA issuer key and loopback TLS
certificate, starts the existing stateless Lab resource server, and never
contacts an external service. Remote mode requires an owner-issued short-lived
access token entered through getpass; tokens are never written to evidence.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import getpass
import hashlib
import importlib.metadata
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ISSUER = "https://issuer.example.invalid/"
SUBJECT = "synthetic-owner"
CLIENT_ID = "synthetic-client"
KEY_ID = "fixture-1"
SCOPE = "lab:read"
EXPECTED_SDK = "2.3.0"


def fixtures() -> dict[str, tuple[dict, dict]]:
    report = json.loads((HERE / "BASELINE_RERUN_RPC.json").read_text(encoding="utf-8"))
    seen: dict[str, tuple[dict, dict]] = {}
    for row in report["stdio"]:
        request = row.get("request", {})
        response = row.get("response", {})
        params = request.get("params", {})
        result = response.get("result", {})
        if request.get("method") == "tools/call" and not result.get("isError"):
            name = params.get("name")
            args = params.get("arguments")
            expected = result.get("structuredContent")
            if isinstance(name, str) and isinstance(args, dict) and isinstance(expected, dict):
                seen[name] = (args, expected)
    if len(seen) != 23:
        raise RuntimeError(f"fixture_inventory_invalid:{len(seen)}")
    return seen


def sdk_imports():
    version = importlib.metadata.version("mcp")
    if version != EXPECTED_SDK:
        raise RuntimeError(f"official_mcp_sdk_version_mismatch:{version}")
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    import httpx2
    return Client, streamable_http_client, httpx2


async def qualify(url: str, token: str, ca_file: str | None, output: str, *, local: bool):
    Client, streamable_http_client, httpx2 = sdk_imports()
    expected_tools = fixtures()
    tls = ssl.create_default_context(cafile=ca_file) if ca_file else ssl.create_default_context()
    report: dict = {
        "sdk": f"mcp=={EXPECTED_SDK}",
        "transport": "official SDK v2 Streamable HTTP",
        "scope": "synthetic loopback fixture" if local else "owner-authorized remote MCP server",
        "server_version": "0.3.0",
        "protocol_version": None,
        "discovered_tools": 0,
        "passes": 0,
        "failures": 0,
        "sessions": [],
    }

    async def one_session(repeat: int):
        session_record = {"repeat": repeat, "tools": [], "parallel": "UNVERIFIED"}
        async with httpx2.AsyncClient(
            verify=tls,
            headers={"Authorization": "Bearer " + token},
            trust_env=False,
            follow_redirects=False,
            timeout=httpx2.Timeout(30.0, read=30.0),
        ) as http_client:
            transport = streamable_http_client(url, http_client=http_client)
            async with Client(transport) as client:
                info = client.server_info
                if info is None or info.version != "0.3.0":
                    raise AssertionError("server_info_mismatch")
                protocol = str(client.protocol_version)
                if protocol not in ("2025-03-26", "2025-06-18", "2025-11-25"):
                    raise AssertionError(f"protocol_version_unexpected:{protocol}")
                report["protocol_version"] = protocol
                listed = await client.list_tools()
                discovered = {tool.name: tool for tool in listed.tools}
                if set(discovered) != set(expected_tools):
                    raise AssertionError("tool_discovery_set_mismatch")
                if len(discovered) != 23:
                    raise AssertionError("tool_discovery_count_mismatch")
                report["discovered_tools"] = len(discovered)

                for name, (args, expected) in expected_tools.items():
                    started = time.perf_counter()
                    result = await client.call_tool(name, args)
                    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
                    if result.is_error or result.structured_content != expected:
                        raise AssertionError(f"positive_result_mismatch:{name}")
                    text_blocks = [getattr(block, "text", None) for block in result.content if getattr(block, "type", None) == "text"]
                    if not text_blocks or json.loads(text_blocks[0]) != expected:
                        raise AssertionError(f"text_content_mismatch:{name}")
                    bad = await client.call_tool(name, {})
                    if not bad.is_error:
                        raise AssertionError(f"negative_schema_case_accepted:{name}")
                    canonical = json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    session_record["tools"].append({
                        "name": name,
                        "positive": "PASS",
                        "negative_empty_arguments": "PASS",
                        "duration_ms": elapsed_ms,
                        "expected": expected,
                        "actual": result.structured_content,
                        "result_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                    })
                    report["passes"] += 2

                async def parallel_call(name: str):
                    args, expected = expected_tools[name]
                    result = await client.call_tool(name, args)
                    if result.is_error or result.structured_content != expected:
                        raise AssertionError(f"parallel_result_mismatch:{name}")
                    return name

                first_four = list(expected_tools)[:4]
                parallel_names = await asyncio.gather(*(parallel_call(name) for name in first_four))
                if set(parallel_names) != set(first_four):
                    raise AssertionError("parallel_tool_set_mismatch")
                session_record["parallel"] = {"count": 4, "state": "PASS", "tools": parallel_names}
                report["passes"] += 1

                try:
                    unknown = await client.call_tool("__execution_guard_lab_unknown__", {})
                    if not unknown.is_error:
                        raise AssertionError("unknown_tool_accepted")
                    session_record["unknown_tool"] = "PASS"
                except Exception as exc:
                    # The SDK may raise MCPError for JSON-RPC method/tool errors.
                    if type(exc).__name__ not in ("MCPError", "McpError"):
                        raise
                    session_record["unknown_tool"] = "PASS_SDK_ERROR"
                report["passes"] += 1
        return session_record

    for repeat in (1, 2):
        async with asyncio.timeout(120):
            report["sessions"].append(await one_session(repeat))

    report["status"] = "PASS"
    Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def make_local_fixture(output: str):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import jwt

    with tempfile.TemporaryDirectory(prefix="eglab-sdk-v2-") as temp:
        root = Path(temp)
        auth_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        tls_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = dt.datetime.now(dt.timezone.utc)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(tls_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=1))
            .not_valid_after(now + dt.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(tls_key, hashes.SHA256())
        )
        cert_path = root / "tls.crt"
        key_path = root / "tls.key"
        public_path = root / "auth.pem"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(tls_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        public_path.write_bytes(auth_key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        resource = f"https://127.0.0.1:{port}/mcp"
        env = {
            **os.environ,
            "LAB_RESOURCE": resource,
            "LAB_ISSUER": ISSUER,
            "LAB_OWNER_SUB": SUBJECT,
            "LAB_CLIENT_ID": CLIENT_ID,
            "LAB_KEY_ID": KEY_ID,
            "LAB_PUBLIC_KEY_FILE": str(public_path),
            "LAB_TLS_CERT": str(cert_path),
            "LAB_TLS_KEY": str(key_path),
            "LAB_BIND": "127.0.0.1",
            "LAB_PORT": str(port),
        }
        process = subprocess.Popen(
            [sys.executable, "-B", str(HERE / "run_local_tls_fixture.py")],
            cwd=HERE,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        token = jwt.encode(
            {
                "iss": ISSUER,
                "sub": SUBJECT,
                "aud": resource,
                "client_id": CLIENT_ID,
                "scope": SCOPE,
                "iat": int(time.time()) - 1,
                "exp": int(time.time()) + 120,
            },
            auth_key,
            algorithm="RS256",
            headers={"kid": KEY_ID, "typ": "at+jwt"},
        )
        context = ssl.create_default_context(cafile=str(cert_path))
        try:
            import httpx2
            for _ in range(100):
                if process.poll() is not None:
                    err = process.stderr.read(1000) if process.stderr else ""
                    raise RuntimeError("local_tls_server_exited:" + err[:500])
                try:
                    with httpx2.Client(verify=context, trust_env=False, timeout=1.0) as client:
                        response = client.get(resource[:-4] + "/health")
                        if response.status_code == 200 and response.json().get("version") == "0.3.0":
                            break
                except Exception:
                    time.sleep(0.05)
            else:
                raise RuntimeError("local_tls_server_readiness_timeout")
            asyncio.run(qualify(resource, token, str(cert_path), output, local=True))
        finally:
            process.terminate()
            try:
                _, err = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                _, err = process.communicate()
            if process.returncode not in (0, -15):
                raise RuntimeError("local_tls_server_shutdown_failed:" + (err or "")[:500])
            if err and "Traceback" in err:
                raise RuntimeError("local_tls_server_traceback:" + err[:500])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url")
    parser.add_argument("--ca")
    parser.add_argument("--output", default="SDK_EVIDENCE_V2.json")
    parser.add_argument("--check-install", action="store_true")
    parser.add_argument("--local-fixture", action="store_true")
    args = parser.parse_args()
    try:
        sdk_imports()
    except (ImportError, importlib.metadata.PackageNotFoundError, RuntimeError) as exc:
        print("BLOCKED: official MCP Python SDK 2.3.0 unavailable (" + type(exc).__name__ + ")", file=sys.stderr)
        return 3
    if args.check_install:
        print("Official MCP SDK 2.3.0 import OK; server calls not performed")
        return 0
    if args.local_fixture:
        make_local_fixture(args.output)
        print("Official MCP SDK 2.3.0 loopback TLS qualification PASS")
        return 0
    parsed = urlsplit(args.url or "")
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path != "/mcp":
        parser.error("a verified HTTPS /mcp URL is required")
    token = getpass.getpass("Access token issued for this Lab (not stored): ")
    if not token:
        return 2
    try:
        asyncio.run(qualify(args.url, token, args.ca, args.output, local=False))
    except Exception as exc:
        print("FAIL: " + type(exc).__name__ + " (token and raw exception omitted)", file=sys.stderr)
        return 1
    print("Official MCP SDK 2.3.0 remote qualification PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
