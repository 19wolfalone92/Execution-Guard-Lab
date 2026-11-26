# Execution Guard Lab 0.4.0 — Qualification status

Date: 2026-11-26
Status: PARTIAL / HOLD

## Verified recovery

- Restored Execution Guard checkpoints: 0.2.0 revision 1, 0.3.0 revision 2, and connection audit revision 1.
- Restored the original `Execution-Guard-Lab-0.3.0.zip` from the Library.
- Verified exact size 258,563 bytes and SHA-256 `2e68e71968a70c32449364604973ffd4d69da31f14c475cf25551a0b766382c5`.
- ZIP integrity: PASS; 65 unique entries; 64/64 manifest checks PASS; no unsafe ZIP paths or symlink entries.
- Restored all 23 named tools. The registry contains 23 unique names and its set exactly matches the required inventory.
- Reproduced the complete existing test suite locally: 364/364 PASS.
- Existing acceptance ledger validation: PASS.
- High-confidence credential scan found no PEM private keys, GitHub PATs, OpenAI keys, Cloudflare API tokens, bearer-token literals, or compact JWTs in the source archive. This is a heuristic scan, not a full secret-scanner attestation.

## Dependency findings

The restored environment currently contains `cryptography==46.0.4` and `PyJWT==2.13.0`. The fail-closed production preflight correctly rejects both versions because the qualified runtime pins are `cryptography==50.0.2` and `PyJWT==2.15.1`.

Official advisory research confirms that PyJWT 2.13.0 is affected by multiple 2026 advisories fixed in 2.14.0, including CVE-2026-102270 and related JWK/JWT validation issues. `cryptography` 46.0.4 is within the affected range for CVE-2026-39892; the advisory lists 46.0.7 as fixed. The proposed 50.0.2 and 2.15.1 pins are newer than those fixed versions and are published on PyPI with provenance metadata.

The local environment has no DNS access to PyPI. A clean virtual-environment install failed during resolution (`Temporary failure in name resolution`), so the new dependency versions, lock file, and `pip-audit` result are not yet qualified. The 364 PASS result therefore does **not** qualify the current dependency graph for production.

The official MCP Python SDK 1.30.0 is the maintenance 1.x line. The current stable line is v2; candidate qualification has been updated to `mcp==2.3.0` and `httpx2==2.16.2`. A new independent SDK v2 probe and a secrets-free GitHub Actions qualification workflow have been prepared. They have not yet executed because the SDK cannot be installed in this offline environment.

## GitHub state

Repository: `19wolfalone92/Execution-Guard-Lab`

Confirmed main SHA: `d356c7862d50ee369b126aa897748c3b0f8989e8`

The repository is currently **Public**. The accessible repository snapshot contains only the read-only Cloudflare connection-check workflow; the source archive has not yet been published to a working branch. The linked GitHub integration reports admin/push permissions. Repository rulesets query returned an empty list; branch-protection inspection returned HTTP 403 from the connector and therefore remains UNVERIFIED.

## Cloudflare state and safety hold

The last read-only diagnostic run `45882703773` succeeded. It confirmed the Cloudflare token is active, matches the specified account, and can read Workers, the Workers subdomain, KV, and D1. R2 returned HTTP 403 / code 10042 and is not required.

The token policy includes broad/unspecified and user-scope resource classifications in addition to the target account. Expiration and IP restrictions are absent. Declared write permissions are not proof of actual write access. Exclusive account isolation is not established; therefore **no Cloudflare mutation, Worker creation, deployment, D1/KV write, or public exposure is permitted at this stage**. No such operation was attempted.

## Architecture research

Cloudflare's current Remote MCP guide supports Streamable HTTP Workers and OAuth through separate authorization-server and resource-server roles using Workers OAuth Provider. Cloudflare Python Workers use the Pyodide/PyEmscripten package model; the existing CPython ASGI + Uvicorn deployment is not directly portable without an adapter and package compatibility work. Cloudflare documents a 10 ms CPU limit on the Free plan and up to 5 minutes on Paid, with 128 MB memory; CPU-heavy tools and archive/AST processing may therefore require measured limits or an approved paid plan. No paid service has been enabled.

## Not yet qualified

- Updated runtime install and reproducible hash lock.
- Full dependency audit against the resolved graph.
- Full 364-test rerun on updated dependencies.
- Official MCP SDK v2.3.0 wire-level run.
- Cloudflare Python/TypeScript architecture execution.
- Isolated Cloudflare token scope and write/deploy permissions.
- Real OAuth authorization server, PKCE, consent, refresh and revocation.
- Production preflight on the updated environment.
- Cloudflare deployment, permanent HTTPS endpoint, remote MCP 23/23.
- ChatGPT registration, ChatGPT tool calls, and cross-session stability.

## Isolation guarantees

The main Execution Guard Pro repository, PR #5, checkpoint 43, and support case #21118282 were not modified. No previously blocked GitHub operation was retried or bypassed. The Lab repository and Cloudflare account remain separate from the main Pro project.
