# EXECUTION GUARD LAB 0.8.0 — Qualification report

**Date:** 2026-11-27  
**Status:** PARTIAL / HOLD — not a production release  
**Repository:** 19wolfalone92/Execution-Guard-Lab  
**Branch:** qualification/cloud-runtime-oauth-20261127  
**Qualified code commit:** 83892d1c00aff04dab56b3db86e7c38ccdb8b116  
**Parent:** c1fe9d871d10385a3ec7b1d938936d4ca2d27801  
**Restored checkpoint:** execution-guard-lab-0-7-0, revision 2 (read and re-read through Execution Guard Pro)  
**Pro checkpoint:** execution-guard-0-6-0, revision 43 (read-only verification)

## 1. Executive result

The Lab was restored from its exact 0.7.0 Git tree and its previously recorded 54-gate acceptance ledger. The Pro/Lab comparison is documented across all 34 requested architecture dimensions. The HTTPS diagnostic path was hardened, and the historical Cloudflare probe now has fail-safe cleanup for a temporary worker, including an ambiguous upload response.

The local qualification is stronger than the 0.7.0 baseline:

- **412/412 pytest PASS** (409 baseline + 3 regression tests).
- **MCP SDK v2: 96/96 PASS**, 23 tools discovered over a synthetic loopback TLS fixture.
- **Integrated local MCP: PASS** — 23 tools, 46 positive/negative checks, 23 stress checks, two synthetic sessions; 47 Python tests and 12 Node tests passed.
- **Distributed admission: 11/11 PASS** across separate local Worker instances sharing one SQLite Durable Object.
- **Python Workers local workerd: 69/69 PASS**, plus parallel calls.
- **pip-audit:** 35 dependencies, 0 reported vulnerabilities. **npm audit:** 0 vulnerabilities.
- All three new qualification workflows completed successfully.

These are local/synthetic qualifications. They do **not** establish a public Lab endpoint, real Lab OAuth, Cloudflare production CPU/RAM, remote MCP, or ChatGPT availability.

## 2. What blocked Lab while Pro worked

The code comparison shows several material differences:

1. Pro production is a single JavaScript Worker using the proven OAuth Provider, a live workers.dev route, D1 for durable application state, and KV for OAuth-provider state.
2. Pro candidate 0.6.0 used a direct Wrangler Preview deployment with isolated preview resources and Node fetch smoke checks. The direct preview deployment passed; a separate automatic Worker Builds path had credential errors.
3. Lab has a JS Gateway plus a private Python Worker through a Service Binding, a SQLite-backed Durable Object for admission, and KV-backed OAuth provider state. Its integrated Wrangler files are local fixtures with workers.dev and preview routes disabled.
4. Lab's historical probe used the Cloudflare REST API for deployment and Python urllib for the public HTTPS smoke. The upload, version activation and subdomain enablement completed; the public smoke then stopped with a generic authorization error. The exact HTTP response was not retained.
5. The Lab production path is currently held by an explicit release guard. No Lab public endpoint exists.

The Pro architecture is a useful reference, but not a drop-in configuration. Resource IDs, OAuth clients, secrets, databases, endpoints and production deployments were not copied.

See PRO_VS_LAB.csv for the 34-row matrix and PRO_VS_LAB_SOURCE_MAP.md for immutable Pro/Lab source paths and commit references.

## 3. HTTPS root-cause determination

**Result: UNVERIFIED.**

The historical failed job (run 45906590372, job 140204684223) records a generic BLOCKED / HTTPS authorization rejected after the test worker had been uploaded, activated and exposed through the temporary workers.dev subdomain. It does not preserve the exact status, CF-Ray, response headers or response body. The old 401/403 exception branch raised a generic stop without retaining that evidence.

The Python urllib client had no explicit User-Agent. Cloudflare's current Error 1010 documentation explicitly lists requests to *.workers.dev with the default Python urllib User-Agent as a common cause. It also says Browser Integrity Check applies to workers.dev and such blocks may not appear in zone Security Events or Worker logs; support cannot override the security setting, and BIC cannot be turned off for workers.dev. This makes BIC/Error 1010 the leading technical hypothesis. It still does not prove the historical incident received Error 1010: the exact status, CF-Ray, headers and body were discarded. Other edge policies or an alternative response therefore cannot be excluded.

No request was repeated, no User-Agent or route was changed, no alternate network/client was used, and no Cloudflare security control was bypassed.

## 4. HTTP diagnostic and probe-safety changes

Files changed in the qualified code commit:

- diagnostics/http_evidence.py
- diagnostics/test_http_evidence.py
- cloud_runtime/write_probe.py
- cloud_runtime/test_write_probe.py

The new evidence row captures UTC time, HTTP status, CF-Ray, Content-Type, Server, allowlisted error-code/body hints, worker/deployment/version identifiers, source SHA, request correlation ID, duration, category and stop reason. It never stores arbitrary response bodies, cookies, Authorization headers, tokens, redirect targets or exception messages. Body hints remain explicitly unverified.

The probe remains disabled from command-line execution by its HOLD guard. If an explicitly authorized test is later run, cleanup first reads back the exact collision-checked worker name, disables its temporary subdomain, deletes only that temporary worker and verifies absence. The cleanup path is covered by synthetic tests, including a lost upload response. No Cloudflare write was performed in this qualification.

## 5. Pro vs Lab and deployment findings

- Pro production main remains a61f1061b91dbabce2bb3ccf66ba710589b21808.
- Pro candidate 097466cd33842f6dafabc5e3411c84fb6f1e5d52 remains in open/draft PR #5; it is not the production 0.5.0 plugin.
- The currently connected Pro plugin returned an authenticated, owner-verified identity and exposes six production tools. The 0.6.0 candidate source declares a larger surface, but that is not the same as the live production plugin.
- Lab's current integrated configuration has no public workers.dev/preview route. No Cloudflare deployment or remote endpoint was created.
- The Pro and Lab Cloudflare account IDs and security settings cannot be compared from the available public source and masked secrets. Same-account equivalence is unverified.

## 6. OAuth and identity

Lab's code uses OAuth Provider 1.4.0, DCR, PKCE S256, a GitHub identity adapter, 900-second access-token TTL and 604800-second refresh-token TTL. The local integrated flow exercises discovery, authorization, refresh, revoke and denial using a synthetic identity.

There is no real Lab OAuth App registration/credential set and no real Lab owner sign-in. Lab OAuth state uses KV; its global atomicity, refresh-token replay protection and revocation consistency have not been proven. The local synthetic tests do not satisfy Gate BI, BJ, BK or BL.

Pro's working owner identity is not evidence that Lab's own OAuth identity works. No Pro credentials or database were reused.

## 7. Distributed security and admission

The Lab admission Durable Object is SQLite-backed and passes 11/11 local checks: global four-slot concurrency, cross-Worker sharing, wrong-client release rejection, duplicate-release rejection, restart persistence and capacity recovery after confirmed completion.

The unresolved case is an operation whose execution may still be running after the Gateway loses its response. The current policy remains fail-closed. A lease timeout alone is not proof that the Python Worker stopped; no time-only slot release was added. Heartbeats, fencing and a durable worker-side terminal acknowledgement still need a separately qualified design.

OAuth state remains in KV and is not covered by the admission DO's atomic transactions.

## 8. CPU, RAM and Cloudflare Free

The 0.8.0 source-bundle benchmark contains 92 CPython-native scenarios across 23 tools (baseline, stress, negative and representative schema-boundary cases; 20 samples per case). Two source-bundle samples on the same code tree show normal host-load variation:

| Tool / case | Run e04a p50 / p95 | Run 03ff p50 / p95 | Peak Python allocation |
|---|---:|---:|---:|
| code_structure_analyze, stress | 17.579 / 29.184 ms | 19.941 / 20.145 ms | about 9.93 MB |
| code_structure_analyze, schema_boundary | 15.228 / 15.898 ms | 18.550 / 19.077 ms | about 9.93 MB |
| time_series_analyze, stress | 2.440 / 2.452 ms | 2.672 / 2.788 ms | about 8.5 KB |
| time_series_analyze, schema_boundary | 5.455 / 5.485 ms | 6.306 / 6.386 ms | about 18.4 KB |

These are native CPython timings, not Cloudflare isolate CPU measurements. Local workerd executed all 69 vectors, but the evidence explicitly has worker_cpu_ms=null and worker_ram_bytes=null. Its host process RSS is not per-isolate Cloudflare RAM and must not be presented as such.

Cloudflare's current Free limits include 100,000 Worker requests/day, 10 ms CPU per HTTP request, 128 MB per isolate, 50 subrequests/request and six simultaneous outgoing connections. SQLite-backed Durable Objects are available on Free; their Free allowance includes 100,000 DO requests/day, 13,000 GB-s/day, 5 million row reads/day, 100,000 row writes/day and 5 GB total SQLite storage. The current admission path makes two DO requests per admitted tool call, so the DO request allowance alone gives a theoretical ceiling of 50,000 calls/day before other traffic; row-write usage may constrain it further.

The dense AST native timing is a material Free-tier risk, not proof of a Cloudflare overrun. Free compatibility remains UNVERIFIED until an authorized Cloudflare preview records real isolate CPU and RAM. No paid plan was activated.

## 9. ChatGPT MCP eligibility and result

The Lab has 0/23 remote tools, 0/23 ChatGPT-discovered tools and 0/23 ChatGPT calls because it has no public MCP endpoint and no real Lab OAuth.

Current OpenAI documentation states that custom MCP connections are available to Business and Enterprise/Edu workspaces; Pro users can connect custom MCP servers with read/fetch permissions; full MCP is currently limited to Business and Enterprise/Edu. The current account plan is Plus, so a custom Lab MCP connection cannot be created from this account. Lab's tools use the read-only lab:read scope; Pro's read/fetch mode could fit that surface, but Plus is not eligible. Custom connection creation is web-only.

The existing Execution Guard Pro plugin was not changed.

## 10. Gate result

The original 54 gates A-BB are preserved exactly from the 0.7.0 ledger. The 25 new gates BC-CA have been appended.

79 gates total: 30 PASS, 14 PARTIAL, 33 BLOCKED, 2 UNVERIFIED, 0 FAIL.

The release remains PARTIAL / HOLD. In particular, BE is UNVERIFIED; BG, BI-BL, BN-BO, BQ-BU, BV and BZ-CA remain blocked.

## 11. Production preflight and rollback

Production preflight is HOLD. No Lab production deployment, OAuth secret registration, public endpoint, ChatGPT app registration, paid Cloudflare plan, or rollback was performed. The static probe's cleanup logic is locally tested only; it is not production rollback evidence.

Before any cloud qualification, the owner must authorize a single controlled diagnostic or provide the missing Cloudflare edge/security evidence. Then Lab must receive its own OAuth App configuration through the secret store, pass real owner identity, qualify atomic OAuth storage, deploy an isolated Wrangler Preview, and complete remote MCP tests. Only then can ChatGPT connection eligibility be used.

## 12. Pro immutability and final state

Execution Guard Pro was accessed read-only. Its repository, production deployment, OAuth configuration, databases, tokens, endpoints and ChatGPT plugin were not changed. The Pro checkpoint was read for verification only.

Final decision: keep Lab on HOLD. Local architecture and diagnostics improved; the actual success criterion—an independently working 23-tool Lab MCP app in ChatGPT—has not been reached.
