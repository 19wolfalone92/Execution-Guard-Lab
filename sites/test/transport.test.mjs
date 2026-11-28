import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { acquire } from "../worker/admission.js";
import { createWorker } from "../worker/handler.js";
import { endpoint, headers, rpc, send, setup } from "./runtime.mjs";

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const rawCall = (name, args) => rpc("tools/call", { name, arguments: args });

test("built artifact: native MCP transport and original diagnostics", async t => {
  const { mf, db, sessions: [agent, second] } = await setup(["primary", "second"]);
  t.after(() => mf.dispose());

  await t.test("catalog and discover", async () => {
    const d = await (await send(agent, rpc("server/discover"))).json();
    assert.deepEqual(d.result.supportedVersions, ["2026-07-28"]);
    assert.equal(d.result.serverInfo.version, "1.0.0");
    const r = await (await send(agent, rpc("tools/list"))).json();
    const canonical = JSON.parse(await readFile(new URL("../worker/catalog.json", import.meta.url), "utf8"));
    assert.deepEqual(r.result.tools.map(row => row.name), ["lab_health", "lab_sha256", "lab_numeric_verify", ...canonical.map(row => row.name)]);
    for (const tool of r.result.tools) {
      assert.equal(tool.annotations.readOnlyHint, true);
      assert.equal(tool.inputSchema.additionalProperties, false);
      assert.equal(tool.outputSchema.additionalProperties, false);
      assert.ok(tool.outputSchema.required.includes("request_id"));
    }
  });

  await t.test("home and identity gate", async () => {
    const page = await agent.fetch("https://synthetic-owner.example.invalid/");
    assert.match(await page.text(), /1\.0\.0/);
    assert.match(page.headers.get("content-security-policy"), /frame-ancestors 'self' https:\/\/chatgpt.com/);
    const anonymous = await send(agent, rawCall("lab_health", {}), { "content-type": "application/json" });
    assert.equal(anonymous.status, 401);
    const failClosed = await createWorker(null).fetch(new Request(endpoint, {
      method: "POST", headers, body: rawCall("lab_health", {}),
    }));
    assert.equal(failClosed.status, 503);
  });

  await t.test("strict envelope rejects malformed, duplicate, unicode and numeric cases", async () => {
    const bad = [
      "{", '{"id":1,"\\u0069d":2}', '{"x":"\\ud800"}', '{"x":1e999}', '{"x": NaN}', '{"x": Infinity}',
      "[".repeat(30) + "0" + "]".repeat(30),
    ];
    for (const source of bad) assert.equal((await send(agent, source)).status, 400);
    assert.equal((await send(agent, " ".repeat(131073))).status, 413);
    assert.equal((await send(agent, "{}", { "content-type": "text/plain" })).status, 415);
    assert.equal((await agent.fetch(endpoint)).status, 405);
    assert.equal((await (await send(agent, rawCall("unknown", {}))).json()).error.code, -32602);
  });

  await t.test("original diagnostics and Unicode match independent Node or BigInt references", async () => {
    const count = new Set();
    async function check(name, args, expected) {
      const r = await (await send(agent, rawCall(name, args))).json();
      const { request_id, ...value } = r.result.structuredContent;
      assert.match(request_id, uuid);
      count.add(request_id);
      assert.deepEqual(value, expected);
      assert.deepEqual(JSON.parse(r.result.content[0].text), r.result.structuredContent);
    }
    await check("lab_health", {}, { version: "1.0.0", status: "ok" });
    await check("lab_health", {}, { version: "1.0.0", status: "ok" });
    for (const text of ["", "abc", "🐺".repeat(4096)]) {
      await check("lab_sha256", { text }, { sha256: createHash("sha256").update(text).digest("hex") });
    }
    for (const values of [[0], [-3, 4, 12], [-7, 0, 3, 12, 1e6, -1e6], Array.from({ length:128 }, (_, i) => i%2 ? -1e6 : 1e6)]) {
      const exact = values.map(BigInt);
      await check("lab_numeric_verify", { values }, {
        count: values.length, sum: Number(exact.reduce((a,b) => a+b,0n)),
        sum_of_squares: Number(exact.reduce((a,b) => a+b*b,0n)),
      });
    }
    assert.equal(count.size, 9);
    for (const [name, args] of [
      ["lab_health",{ extra:true }], ["lab_sha256",{ text:123 }], ["lab_sha256",{ text:"a".repeat(4097) }],
      ["lab_numeric_verify",{ values:[] }], ["lab_numeric_verify",{ values:Array(129).fill(0) }],
      ["lab_numeric_verify",{ values:[1_000_001] }], ["lab_numeric_verify",{ values:[1.25] }],
    ]) {
      const result = (await (await send(agent, rawCall(name, args))).json()).result;
      assert.equal(result.isError, true);
      assert.match(result.content[0].text, /Invalid tool arguments\. Request ID [a-f0-9-]{36}$/);
    }
  });

  await t.test("admission serializes across worker instances and recovers after completion", async () => {
    const slots = await Promise.all([1,2,3,4].map(i => acquire(db, "held-" + i)));
    assert.ok(slots.every(slot => slot.status === 200));
    const closed = await send(second, rawCall("lab_health", {}));
    assert.equal(closed.status, 429);
    assert.equal(closed.headers.get("retry-after"), "60");
    for (const slot of slots) assert.ok(await slot.release());
    assert.equal((await send(agent, rawCall("lab_health", {}))).status, 200);
    assert.equal((await send(second, rawCall("lab_health", {}))).status, 200);
  });

  await t.test("rate boundary, rejection and window recovery without a load test", async () => {
    const start = await db.prepare("SELECT count(*) n FROM lab_admission").first("n");
    await db.prepare(`WITH RECURSIVE fixtures(i) AS (SELECT 1 UNION ALL SELECT i+1 FROM fixtures WHERE i<?)
      INSERT INTO lab_admission SELECT 'fixture-' || i, unixepoch(), 0 FROM fixtures`).bind(159-start).run();
    assert.equal((await send(second, rawCall("lab_numeric_verify", { values:[0] }))).status, 200);
    assert.equal((await send(agent, rawCall("lab_numeric_verify", { values:[0] }))).status, 429);
    await db.prepare("UPDATE lab_admission SET started=unixepoch()-60 WHERE active=0").run();
    assert.equal((await send(agent, rawCall("lab_numeric_verify", { values:[0] }))).status, 200);
    assert.equal(await db.prepare("SELECT count(*) n FROM lab_admission").first("n"), 1);
  });
});
