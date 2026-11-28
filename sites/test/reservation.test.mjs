import assert from "node:assert/strict";
import test from "node:test";
import { acquire, activate, release, reservation, reserve } from "../worker/admission.js";
import { headers, rpc, send, setup } from "./runtime.mjs";

const count = db => db.prepare("SELECT count(*) AS n FROM lab_admission WHERE active=1").first("n");
const expire = (db, t) => db.prepare("UPDATE lab_admission SET reserved_until=unixepoch()-1 WHERE lease=? AND active=0").bind(t.lease).run();

test("expiry fences an abandoned reservation and capacity recovers at four", async t => {
  const {mf, db}=await setup();
  t.after(() => mf.dispose());
  const items = Array.from({ length: 4 }, (_, i) => reservation("pending-" + i));
  for (const item of items) assert.equal((await reserve(db, item)).status, 200);
  assert.equal(await count(db), 0);
  assert.equal((await acquire(db, "fifth")).status, 429);
  for (const item of items) {
    await expire(db, item);
    assert.equal((await activate(db, item)).status, 429);
  }
  await db.prepare("UPDATE lab_admission SET started=unixepoch()-90 WHERE active=0").run();
  const stale = { ...items[0], until: Math.floor(Date.now() / 1000)-1 };
  assert.equal((await reserve(db, stale)).status, 429);
  assert.equal((await activate(db, stale)).status, 429);
  const running = await Promise.all(Array.from({ length: 4 }, (_, i) => acquire(db, "new-" + i)));
  assert.ok(running.every(slot => slot.status === 200));
  assert.equal(await count(db), 4);
  assert.equal((await acquire(db, "next")).status, 429);
  for (const slot of running) assert.ok(await slot.release());
  assert.equal(await count(db), 0);
});

test("only one concurrent claimant can start and old fences cannot release it", async t => {
  const {mf, db}=await setup();
  t.after(() => mf.dispose());
  const item = reservation("one");
  assert.equal((await reserve(db, item)).status, 200);
  assert.equal((await reserve(db, item)).status, 429);
  const pair = await Promise.all([activate(db, item), activate(db, item)]);
  assert.deepEqual(pair.map(slot => slot.status).sort(), [200, 429]);
  assert.equal(await count(db), 1);
  assert.equal(await release(db, item.lease, "previous-claimant"), false);
  assert.equal(await count(db), 1);
  const holder = pair.find(slot => slot.status === 200);
  assert.ok(await holder.release());
  assert.ok(await holder.release());
  assert.equal((await activate(db, item)).status, 429);
  assert.equal(await count(db), 0);
});

test("mixed deployments count the same active executions after migration", async t => {
  const {mf, db}=await setup();
  t.after(() => mf.dispose());
  for (let i=0;i<3;i++) {
    await db.prepare("INSERT INTO lab_admission (lease,started,active) VALUES (?,unixepoch(),1)").bind("legacy-"+i).run();
  }
  const item=reservation("new-pending");
  assert.equal((await reserve(db,item)).status,200);
  assert.equal(await count(db),3);
  await db.prepare("INSERT INTO lab_admission (lease,started,active) VALUES ('legacy-4',unixepoch(),1)").run();
  assert.equal((await activate(db,item)).status,429);
  await db.prepare("UPDATE lab_admission SET started=unixepoch()-300 WHERE active=1").run();
  assert.equal((await acquire(db,"unsafe-reclaim")).status,429);
  assert.equal(await count(db),4);
});

test("activation reconciles a lost acknowledgement, repeated outage fails closed", async t => {
  const {mf,db}=await setup();
  t.after(() => mf.dispose());
  for (const mode of ["precommit", "postcommit", "repeated"]) {
    const item = reservation(mode);
    assert.equal((await reserve(db,item)).status,200);
    let tries=0;
    const fault = { prepare: db.prepare.bind(db), async batch(statements) {
      tries++;
      if (mode === "repeated") throw new Error("D1 fault");
      if (tries > 1) return db.batch(statements);
      if (mode === "postcommit") await db.batch(statements);
      throw new Error("D1 fault");
    }};
    const running=await activate(fault,item);
    assert.equal(running.status, mode === "repeated" ? 503 : 200);
    assert.equal(tries,2);
    if (running.release) assert.ok(await running.release());
    assert.equal(await count(db),0);
  }
  assert.equal((await acquire(undefined,"missing-DB")).status,503);
  const result=await acquire(db,"aborted-before-start",{ aborted:true });
  assert.equal(result.status,503);
  assert.equal(await count(db),0);
});

test("replayed JSON-RPC id still gets fresh admission and produces the same result", async t => {
  const {mf,db,sessions:[agent,other]}=await setup(["one","two"]);
  t.after(() => mf.dispose());
  const body=rpc("tools/call",{name:"lab_numeric_verify",arguments:{ values:[-2,0,3] }}, 42);
  const pair=await Promise.all([agent,other].map(async worker => {
    const response=await send(worker,body,headers);
    assert.equal(response.status,200);
    const data=await response.json();
    assert.equal(data.id,42);
    const {request_id,...numeric}=data.result.structuredContent;
    assert.deepEqual(numeric,{count:3,sum:1,sum_of_squares:13});
    return request_id;
  }));
  assert.notEqual(pair[0],pair[1]);
  assert.equal(await count(db),0);
});
