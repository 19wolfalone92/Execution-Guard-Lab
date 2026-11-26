# Проверенные официальные источники (26 ноября 2026)

- OpenAI Custom MCP Servers: https://developers.openai.com/api/docs/guides/custom-mcp-server — web UI, URL/tunnel, OAuth/mixed/no auth, permissions and tool refresh.
- OpenAI Apps SDK / Plugins auth: https://developers.openai.com/plugins/build/auth — protected-resource metadata, exact issuer/audience, PKCE S256, callback modes, CIMD/DCR, token checks and securitySchemes.
- OpenAI plugin server: https://developers.openai.com/plugins/build/mcp-server — SDK and public/private endpoint distinction.
- OpenAI connect and test: https://developers.openai.com/plugins/deploy/connect-chatgpt — connection testing.
- OpenAI Secure MCP Tunnel: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels — customer-hosted client, Platform permission and tunnel setup, OAuth still required when protected.
- MCP 2025-11-25 transport: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports — UTF-8 JSON-RPC, Streamable HTTP, Origin, POST/GET, status codes.
- MCP authorization: https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization — resource metadata, authorization server discovery, OAuth 2.1, token audience and scope.
- Python SDK v1 client docs: https://py.sdk.modelcontextprotocol.io/v1/client/ — ClientSession, streamable_http_client with httpx AsyncClient, send_ping, structuredContent. v2 uses newer protocol; candidate remains legacy handshake.
- Official SDK release: https://pypi.org/project/mcp/1.30.0/ — wheel checksum 666edb5009503e1047c9d60346a756f94b261f05cc2625f23d41c728ffc484d0, published 2026-09-07. Direct public download attempt returned `ERROR: download failed` (tool result); package unavailable. No SDK code substituted.
- MCP SDK security advisory: https://github.com/advisories/GHSA-5h93-6whr-6q8j — redirect vulnerability patched in 1.30.0 / 2.2.0.
- TypeScript SDK: https://ts.sdk.modelcontextprotocol.io/v2/protocol-versions — legacy/modern protocol versions and migration differences.
- Cloudflare Python packages: https://developers.cloudflare.com/workers/languages/python/packages/ ; runtime: https://developers.cloudflare.com/workers/languages/python/how-python-workers-work/ ; limits: https://developers.cloudflare.com/workers/platform/limits/ — Pyodide, package/runtime limitations, CPU and memory constraints.
- Cloudflare OAuth provider: https://github.com/cloudflare/workers-oauth-provider — OAuth server/resource server support; no Lab integration performed.
- PyJWT advisories: https://github.com/advisories/GHSA-w2cx-738m-mc7w ; https://github.com/advisories/GHSA-8wjv-2p76-3863 ; https://github.com/advisories/GHSA-hxm8-2xgr-2p9m ; https://github.com/advisories/GHSA-gvp8-978c-rx2q ; https://github.com/advisories/GHSA-9v7f-9g4p-ffgj . Selected update: https://pypi.org/project/PyJWT/2.15.1/ .
- Cryptography advisories: https://github.com/pypa/advisory-database/blob/main/vulns/cryptography/PYSEC-2026-36.yaml ; https://github.com/advisories/GHSA-537c-gmf6-5ccf . Selected update: https://pypi.org/project/cryptography/50.0.2/ .

Documented capabilities and local test outcomes are distinct. No documented global 6/26 universal cap established by these sources. No public plugin submission performed.
