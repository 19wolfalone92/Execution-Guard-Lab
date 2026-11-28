import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { activate, reserve, reservation } from "../worker/admission.js";
import { kernel } from "../worker/kernel.js";
import { setup } from "./runtime.mjs";

// Standalone process used only by the local hard-stop test.
const [stage, path] = process.argv.slice(2);
const { db } = await setup(["crash-test"], { d1Persist: path });
const item = reservation("interrupted-" + stage);
if (stage === "reserved") {
  item.until = await db.prepare("SELECT unixepoch()+5 AS n").first("n");
}
let absolute = null;
if (stage !== "before") {
  assert.equal((await reserve(db, item)).status, 200);
}
if (stage === "running" || stage === "computed") {
  assert.equal((await activate(db,item)).status, 200);
}
if (stage === "computed") {
  const wasm = await WebAssembly.compile(await readFile(new URL("../dist/server/kernel.wasm", import.meta.url)));
  const stdlib = await readFile(new URL("../worker/stdlib.zip", import.meta.url));
  const output = kernel(wasm, new Uint8Array(stdlib)).call(
    '{"params":{"name":"math_calculate","arguments":{"operation":"add","a":2,"b":3}}}',
    "local-computed-fixture");
  assert.ok(output.startsWith("+"));
  absolute = JSON.parse(output.slice(1)).result;
  assert.equal(absolute, 5);
}
process.send({ item, absolute });
// The parent stops this process and its private workerd group after commit.
