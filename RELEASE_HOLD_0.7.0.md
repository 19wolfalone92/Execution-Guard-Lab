# Lab 0.7.0 — release hold and evidence boundaries

The production and historical write workflows remain HOLD. No cloud API request, original HTTPS request, alternative user agent, route, host or network was used in this qualification. No provider support response or live owner OAuth session has been obtained.

## Historical investigation
The official Error 1010 documentation (updated 24 October 2026) describes BIC rejection of some default library User-Agents, including Python urllib, for workers.dev. This matches the historical client and static test code. The exact status, response body, headers and Ray ID were lost. The cause cannot be attributed from saved evidence alone. The providers' documented handling of ordinary legitimate M2M traffic is not authorization to repeat a previously denied operation without the required historical resolution. Do not retry or weaken protections. Free-plan general technical questions are directed to Community/Discord; private details should be sent only through a supported private provider channel. No public incident details or credentials are included here.

Official references (checked 27 November 2026):
- https://developers.cloudflare.com/workers/configuration/routing/workers-dev/
- https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/
- https://developers.cloudflare.com/support/contacting-cloudflare-support/
- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/durable-objects/platform/pricing/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
- https://developers.cloudflare.com/kv/concepts/how-kv-works/
- https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app
- https://docs.github.com/en/rest/apps/oauth-applications

## Remaining independent qualification boundaries
The single SQLite Durable Object coordinates admission, not OAuth grant storage. KV is eventually consistent; production cross-location grant replay/revocation remains unresolved and mandatory. In-flight ambiguous failures preserve durable slots; a supported recovery procedure must prove drain. No automatic release on elapsed time. The documented Free limits are not measurements of the target account. Two DO requests per admitted MCP call consume quotas; rate limits and admission cannot alone guarantee daily Free eligibility. The AST dense maximum source case remains a resource concern. Existing schema limits, 128 KiB request and 1 MiB response limits are preserved, not silently reduced. Native CPU/allocations, local workerd timings and HTTP timings are different metrics. The boundary examples maximize specified dimensions, not every possible data arrangement or encoding. No arbitrary CPU cutoff or truncation is represented as a successful result.

## Reproduction
The source-bundle workflow packages exact Git tree blobs separately from live qualification evidence. Historical reports in the source tree retain their original scope; they are not new evidence. No runtime secrets are required by the local qualification workflows. Actual production release remains blocked by `integrated/preflight.py` and the held workflow; no endpoint or verified callback URL exists.
