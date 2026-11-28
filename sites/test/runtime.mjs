import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { Miniflare, convertV4MiniflareOptions } from "miniflare";

const server = fileURLToPath(new URL("../dist/server/", import.meta.url));
const database = "execution-guard-lab-test";
const migrations = ["0000_admission", "0001_reservation_fence"];
export const endpoint = "https://synthetic-owner.example.invalid/mcp";
export const headers = { "content-type": "application/json", "oai-authenticated-user-id": "synthetic-site-owner" };

export async function setup(names = ["session1"], { modules = server, d1Persist, connectOnly = false, legacy = false } = {}) {
  if (!modules.endsWith("/")) modules += "/";
  const mf = new Miniflare(convertV4MiniflareOptions({
    resourcePersistencePath: d1Persist,
    workers: names.map(name => ({
      name, compatibilityDate: "2026-04-23", modulesRoot: modules,
      modules: [
        { type: "ESModule", path: modules + "index.js" },
        { type: "CompiledWasm", path: modules + "kernel.wasm" },
      ],
      d1Databases: { DB: database },
    })),
  }));
  try {
    const db = await mf.getD1Database("DB", names[0]);
    if (!connectOnly) {
      for (const migration of legacy ? migrations.slice(0, 1) : migrations) {
        const text = await readFile(new URL("../drizzle/" + migration + ".sql", import.meta.url), "utf8");
        await db.batch(text.split("--> statement-breakpoint").map(sql => db.prepare(sql)));
      }
    }
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
