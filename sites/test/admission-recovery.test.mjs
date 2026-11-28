import assert from "node:assert/strict";
import test from "node:test";
import { acquire } from "../worker/admission.js";
import { setup } from "./runtime.mjs";

test("admission reconciles missing D1 responses with one bounded retry", async t => {
  const { mf, db } = await setup();
  t.after(() => mf.dispose());
  const active = () => db.prepare("SELECT count(*) n FROM lab_admission WHERE active=1").first("n");

  for (const fault of ["before_commit", "after_commit"]) {
    let attempts = 0;
    const slot = await acquire({
      prepare: db.prepare.bind(db),
      batch: async stmts => {
        if (++attempts !== 1) return db.batch(stmts);
        if (fault === "after_commit") await db.batch(stmts);
        throw new Error("simulated D1 transport failure");
      },
    }, "acquire-" + fault);
    assert.equal(slot.status, 200, fault);
    assert.equal(attempts, 2);
    assert.equal(await active(), 1);
    assert.ok(await slot.release());
    assert.equal(await active(), 0);
  }

  for (const fault of ["before_commit", "after_commit", "persistent"]) {
    let attempts = 0;
    const slot = await acquire({
      batch: db.batch.bind(db),
      prepare(sql) {
        const stmt = db.prepare(sql);
        if (!sql.startsWith("UPDATE")) return stmt;
        return { bind(...args) {
          const bound = stmt.bind(...args);
          return { async run() {
            if (++attempts > 1 && fault !== "persistent") return bound.run();
            if (fault === "after_commit") await bound.run();
            throw new Error("simulated D1 transport failure");
          }};
        }};
      },
    }, "release-" + fault);
    assert.equal(slot.status, 200);
    assert.equal(await slot.release(), fault !== "persistent", fault);
    assert.equal(attempts, 2);
    assert.equal(await active(), fault === "persistent" ? 1 : 0);
  }
});
