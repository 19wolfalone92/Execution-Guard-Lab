import { spawnSync } from "node:child_process";
import { readFile, writeFile, mkdir, cp, rename } from "node:fs/promises";
import { createHash } from "node:crypto";
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
const rows = [];
async function runFixtures(cases, names, output = rows) {
  const { mf, sessions } = await setup(names);
  try {
    for (const fixture of cases) {
      const begin = performance.now();
      const request = `{"jsonrpc":"2.0","id":${JSON.stringify(fixture.id)},"method":"tools/call",`
        + `"params":{"name":${JSON.stringify(fixture.tool)},"arguments":${fixture.wire_arguments}}}`;
      const response = await send(sessions[fixture.session - 1], request);
      const wire = await response.text();
      output.push({ id:fixture.id,status:response.status,response_bytes:Buffer.byteLength(wire),
        client_ms:Number((performance.now()-begin).toFixed(4)),wire,
        response_sha256:createHash("sha256").update(wire).digest("hex") });
    }
  } finally {
    await mf.dispose();
  }
}
const fixtures = JSON.parse(await readFile(vectors, "utf8"));
await runFixtures(fixtures.filter(c => c.case !== "extended"), ["first", "second"]);
await runFixtures(fixtures.filter(c => c.case === "extended"), ["extended"]);
const path = out + "/LOCAL-MCP.json";
await writeFile(path, JSON.stringify({ transport:"MCP 2026-07-28 in Miniflare/workerd, synthetic owner; shared D1", rows }));
if (!python("compare", path, vectors, out)) throw new Error("core qualification failed");

// Restore original Gate O: 23 distinct stress fixtures, 10 rounds. Two
// isolated local databases avoid modifying the real 160/60 production limit.
const stress = fixtures.filter(c => c.case === "stress");
if (stress.length !== 23 || new Set(stress.map(c => c.tool)).size !== 23) throw new Error("stress inventory");
const stressCases = Array.from({length:10}, (_, round) => stress.map(c => ({...c, id:`S${round+1}-${c.tool}`, session:1}))).flat();
const stressRows = [];
async function atomicJson(file, value) {
  await writeFile(file + ".tmp", JSON.stringify(value));
  await rename(file + ".tmp", file);
}
const stressVectors = out + "/STRESS-VECTORS.json";
const stressRaw = out + "/STRESS-RAW.json";
await atomicJson(stressVectors, stressCases);
for (let offset=0; offset<stressCases.length; offset+=115) {
  await runFixtures(stressCases.slice(offset, offset+115), ["stress"], stressRows);
  await atomicJson(stressRaw, {transport:"local Miniflare/workerd, synthetic owner; separate D1 per 115 calls", rows:stressRows});
}
const checked = spawnSync(process.env.LAB_PYTHON ?? "python3", ["-B", "scripts/stress-verify.py", stressVectors, stressRaw, out + "/STRESS-VERIFIED.csv"], {stdio:"inherit"});
if (checked.error || checked.status !== 0) throw checked.error ?? new Error("stress qualification failed");

// Persist the exact tested build, not only its reported hashes. No Site
// publication or credentials are involved. The existing CI artifact uploader
// retains this archive with the raw test evidence.
await cp("drizzle", "dist/.openai/drizzle", {recursive:true});
const pkg = out + "/SITE-RELEASE.tar.gz";
const packed = spawnSync("tar", ["--sort=name", "--mtime=@0", "--owner=0", "--group=0", "--numeric-owner", "-czf", pkg, "dist"], {stdio:"inherit"});
if (packed.error || packed.status !== 0) throw packed.error ?? new Error("release archive failed");
const digest = createHash("sha256").update(await readFile(pkg)).digest("hex");
await writeFile(out + "/SITE-RELEASE.sha256", digest + "  SITE-RELEASE.tar.gz\n");

