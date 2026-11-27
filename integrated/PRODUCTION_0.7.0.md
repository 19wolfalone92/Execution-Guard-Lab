# Production qualification — HOLD

No cloud action, endpoint request, header change or policy change was performed. Historical refusal has not been attributed. The original cloud workflow remains disabled and CLI remains held. Do not use any alternative URL, network or header to evade it.

## Identity (registration deferred)
After a real HTTPS gateway URL has been qualified, use https://github.com/settings/applications/new (separate OAuth App):
- Application name: Execution Guard Lab Identity
- Homepage URL: the verified gateway HTTPS origin (not available yet).
- Authorization callback URL: that same origin + `/callback` (not a currently usable URL).
- Disable device flow; no repository, organization, write or email scopes. This app is solely for identity. Set `GITHUB_OAUTH_CLIENT_ID` in Gateway configuration and `GITHUB_OAUTH_CLIENT_SECRET` in Gateway runtime secrets; never send it in chat or commit it. The adapter verifies the numeric GitHub ID against `OWNER_ID`, requires empty granted scope and never persists the upstream token. The adapter now requires confirmed retirement of the dedicated app token after identity lookup; mock-only tests, upstream live revocation/expiry and real owner sign-in still require qualification.
- OAuth scope lab:read; access 900 s, refresh 604800 s. The existing provider stores grant state in KV; cross-location replay/revocation is not yet strictly qualified. No assertion of instantaneous global revocation.

## Private core, admission and rotation
Use one SQLite-backed Durable Object binding `ADMISSION`, class `Admission`, migration `new_sqlite_classes`, with one object `lab-global-v1` for the whole single-owner Lab. Durable transactions serialize rolling 60s admission: 180 total, 160 per client, 4 in-flight. The client ID is hashed. Admission occurs only after OAuth and bounded body read. Missing binding or storage failure refuses forwarding. A completed response is drained before release; ambiguous failures retain the slot permanently, including restarts. No automated lease expiry/reset. Recovery: stop admissions, obtain evidence that all calls have ended, review stranded slots and approve a dedicated recovery procedure; no administrative reset endpoint is provided. Production restart and failure recovery remain unqualified. Two DO operations per successful request plus rejected requests; storage and duration quotas need measurement. Limits apply to authenticated MCP requests, not general OAuth traffic. Existing per-isolate gate remains an additional local protection. KV is not used as a lock.

Core config: workers_dev=false, preview_urls=false, routes empty, no direct public domain, Service Binding CORE. Generate a distinct random >=32-character internal secret, provision only Gateway and Core. For planned rotation: deploy core with new current plus old previous, switch Gateway current, validate, then remove previous after all prior gateway versions are drained. No rotation or deployment has been executed in cloud. Neither deployment token nor upstream OAuth secret goes to core. Local tests use explicitly synthetic secrets only.

## Release blockers
Historical refusal attribution and supported recovery, owner identity, OAuth replay/revocation across isolates, real cloud isolation, resource limits incl. Free tier, recovery/rollback, remote MCP SDK and ChatGPT remain mandatory. No valid endpoint or live callback exists. `production-config.example.json` is descriptive, not an authorized deployment config. No automatic release workflow.
