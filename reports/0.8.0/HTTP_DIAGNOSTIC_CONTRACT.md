# HTTP evidence contract — Lab 0.8.0

- Exactly one HTTPS GET; redirects are manual and not followed.
- No retry, User-Agent override, alternate client, route, account, token or network.
- The probe is still disabled by its command-line HOLD guard.
- Retained fields: UTC timestamp, status, CF-Ray, Content-Type, safe Server header, allowlisted body indicator, Worker/deployment/version identifiers, source SHA, request correlation ID, duration, category and stop reason.
- Raw response body, cookies, Authorization, bearer tokens, arbitrary headers, redirect URL/query and exception messages are never retained.
- Error codes parsed from a response body are marked response_body_unverified; they are not proof of edge attribution.
- source_attribution remains UNVERIFIED until corroborated by trusted Cloudflare telemetry.
- On an authorized future probe, the temporary Worker is read back by exact name, its temporary route is disabled, the Worker is deleted, and absence is verified. Ambiguous upload responses are reconciled before cleanup.
