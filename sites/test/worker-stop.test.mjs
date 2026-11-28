import assert from "node:assert/strict";
import { fork } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { setTimeout as pause } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { acquire, activate, reserve } from "../worker/admission.js";
import { setup } from "./runtime.mjs";

const fixture = fileURLToPath(new URL("./crash-fixture.mjs", import.meta.url));

async function hardStop(stage, databaseDir) {
  const child = fork(fixture,[stage,databaseDir],{ detached:true,stdio:["ignore","ignore","inherit","ipc"] });
  const stopped = new Promise(resolve => child.once("exit", (_code,signal) => resolve(signal)));
  try {
    return await new Promise((resolve,reject) => {
      const timeout=setTimeout(() => reject(new Error("Fixture did not reach " + stage)), 15000);
      child.once("message", data => { clearTimeout(timeout); resolve(data); });
      child.once("exit", (code,signal) => { clearTimeout(timeout); reject(new Error("Fixture exited " + code + " " + signal)); });
      child.once("error", error => { clearTimeout(timeout); reject(error); });
    });
  } finally {
    if (child.exitCode === null && child.signalCode === null) {
      // SIGKILL only the disposable group created for this fixture.
      process.kill(-child.pid,"SIGKILL");
      assert.equal(await stopped,"SIGKILL");
    }
  }
}

test("local SIGKILL and restart preserve the reservation boundary", { timeout: 60000 }, async t => {
  for (const stage of ["before", "reserved", "running", "computed"]) {
    await t.test(stage, async () => {
      const dir=await mkdtemp(path.join(tmpdir(),"lab-stop-"));
      let mf;
      try {
        const { item, absolute }=await hardStop(stage,dir);
        const reopened=await setup(["reopened"],{ d1Persist:dir,connectOnly:true });
        mf=reopened.mf;
        const db=reopened.db;
        const row=await db.prepare("SELECT active, reserved_until FROM lab_admission WHERE lease=?").bind(item.lease).first();
        if (stage === "before") assert.equal(row,null);
        if (stage === "reserved") {
          assert.deepEqual(row,{ active:0,reserved_until:item.until });
          let remaining=await db.prepare("SELECT ?-unixepoch() AS n").bind(item.until).first("n");
          if (remaining>0) await pause(remaining*1000+30);
          assert.equal((await activate(db,item)).status,429);
          assert.equal((await reserve(db,item)).status,429);
        }
        if (stage==="running" || stage==="computed") {
          assert.deepEqual(row,{active:1,reserved_until:null});
          assert.equal((await activate(db,item)).status,429);
        }
        if (stage==="computed") assert.equal(absolute,5);
        const newer=await acquire(db,"new-"+stage);
        assert.equal(newer.status,200);
        assert.ok(await newer.release());
      } finally {
        if (mf) await mf.dispose();
        await rm(dir,{recursive:true,force:true});
      }
    });
  }
});
