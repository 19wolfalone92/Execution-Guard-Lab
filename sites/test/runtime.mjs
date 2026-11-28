import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { Miniflare, convertV4MiniflareOptions } from "miniflare";

const server = fileURLToPath(new URL("../dist/server/", import.meta.url));
const database = "execution-guard-lab-test";
const migration = new URL("../drizzle/0000_admission.sql", import.meta.url);
export const endpoint = "https://synthetic-owner.example.invalid/mcp";
export const headers = { "content-type": "application/json", "oai-authenticated-user-id": "synthetic-site-owner" };

export async function setup(names = ["session1"]) {
  const mf = new Miniflare(convertV4MiniflareOptions({
    workers: names.map(name => ({
      name, compatibilityDate: "2026-04-23", modulesRoot: server,
      modules: [
        { type: "ESModule", path: server + "index.js" },
        { type: "CompiledWasm", path: server + "kernel.wasm" },
      ],
      d1Databases: { DB: database },
    })),
  }));
  try {
    const db = await mf.getD1Database("DB", names[0]);
    await db.prepare(await readFile(migration, "utf8")).run();
    const sessions = await Promise.all(names.map(name => mf.getWorker(name)));
    return { mf, db, sessions };
  } catch (err) {
    await mf.dispose();
    throw err;
  }
}

export function rpc(method, params, id = 1) {
  return JSON.stringify({ jsonrpc: "2.0", id, method, params });
}

export function send(session, body, supplied = headers) {
  return session.fetch(endpoint, { method: "POST", headers: supplied, body });
}
