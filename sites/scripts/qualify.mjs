import { spawnSync } from "node:child_process";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { send, setup } from "../test/runtime.mjs";

const out = process.argv[2] ?? ".evidence";
await mkdir(out, { recursive:true });
function python(...args) {
  const run = spawnSync(process.env.LAB_PYTHON ?? "python3", ["-B", "scripts/vectors.py", ...args], { stdio: "inherit" });
  if (run.error) throw run.error;
  if (run.status !== 0) process.exitCode = 1;
  return run.status === 0;
}

const vectors = out + "/VECTORS.json";
if (!python("generate", vectors)) throw new Error("fixture generation failed");
const { mf, sessions } = await setup(["first", "second"]);
const rows = [];
try {
  for (const fixture of JSON.parse(await readFile(vectors, "utf8"))) {
    const begin = performance.now();
    const request = `{"jsonrpc":"2.0","id":${JSON.stringify(fixture.id)},"method":"tools/call",`
      + `"params":{"name":${JSON.stringify(fixture.tool)},"arguments":${fixture.wire_arguments}}}`;
    const response = await send(sessions[fixture.session - 1], request);
    const wire = await response.text();
    rows.push({ id:fixture.id,status:response.status,response_bytes:Buffer.byteLength(wire),
      client_ms:Number((performance.now()-begin).toFixed(4)),wire });
  }
} finally {
  await mf.dispose();
}
const path = out + "/LOCAL-MCP.json";
await writeFile(path, JSON.stringify({ transport:"MCP 2026-07-28 in Miniflare/workerd, synthetic owner; shared D1", rows }));
python("compare", path, vectors, out);
