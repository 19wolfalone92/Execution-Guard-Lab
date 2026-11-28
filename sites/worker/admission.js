// The existing active flag is shared with older deployments during rollout.
// A pending reservation has active=0. Only a transaction may make it active.
const reservationSeconds = 30;
const clean = "DELETE FROM lab_admission WHERE active=0 AND started<=unixepoch()-60";
const insert = `INSERT INTO lab_admission (lease, started, active, reserved_until)
  SELECT ?1, unixepoch(), 0, ?2
  WHERE ?2 > unixepoch() AND ?2 <= unixepoch() + 32
    AND (SELECT count(*) FROM lab_admission WHERE active=1 OR reserved_until>unixepoch()) < 4
    AND (SELECT count(*) FROM lab_admission WHERE started>unixepoch()-60) < 160
  ON CONFLICT(lease) DO NOTHING`;
const start = `UPDATE lab_admission SET active=1, reserved_until=NULL, run_token=?3
  WHERE lease=?1 AND active=0 AND run_token IS NULL
    AND reserved_until=?2 AND reserved_until>unixepoch()
    AND (SELECT count(*) FROM lab_admission WHERE active=1)<4`;
const read = "SELECT active, reserved_until, run_token FROM lab_admission WHERE lease=?";
const finish = "UPDATE lab_admission SET active=0 WHERE lease=?1 AND active=1 AND run_token=?2";

export function reservation(lease) {
  return { lease, until: Math.floor(Date.now() / 1000) + reservationSeconds };
}

async function transition(db, lease, prepare, owns, readSql = read) {
  try {
    const results = await db.batch(prepare());
    if (!results.every(r => r.success)) throw new Error("D1 transition unavailable");
    return { status: results.at(-1).meta.changes === 1 ? 200 : 429 };
  } catch {
    // A lost reply can hide a successful commit. Retry with the same inputs
    // and inspect the durable row in the same transaction as the retry.
    try {
      const results = await db.batch([...prepare(), db.prepare(readSql).bind(lease)]);
      if (!results.every(r => r.success)) return { status: 503 };
      return { status: owns(results.at(-1).results[0]) ? 200 : 429 };
    } catch {
      return { status: 503 };
    }
  }
}

export async function reserve(db, { lease, until }) {
  if (!db) return { status: 503 };
  // Retry must also check expiry in D1. An expired row cannot prove a live
  // reservation, even if no later request has cleaned the rate window yet.
  return transition(db, lease,
    () => [db.prepare(clean), db.prepare(insert).bind(lease, until)],
    row => row?.active === 0 && row.reserved_until === until && row.run_token === null,
    read + " AND reserved_until>unixepoch()");
}

export async function release(db, lease, fence) {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const result = await db.prepare(finish).bind(lease, fence).run();
      if (!result.success) continue;
      if (result.meta.changes === 1) return true;
      const [state] = await db.batch([db.prepare(read).bind(lease)]);
      if (!state.success) continue;
      const row = state.results[0];
      // Only inactive rows can be collected. A different fence is never
      // allowed to acknowledge release of a live or reserved record.
      return !row || (row.active === 0 && row.run_token === fence);
    } catch {
      // A repeated uncertain outcome leaves the authoritative state in D1.
    }
  }
  return false;
}

export async function activate(db, { lease, until }) {
  const fence = crypto.randomUUID();
  const result = await transition(db, lease,
    () => [db.prepare(start).bind(lease, until, fence)],
    row => row?.active === 1 && row.run_token === fence);
  if (result.status !== 200) return result;
  return { ...result, release: () => release(db, lease, fence) };
}

export async function acquire(db, lease, signal) {
  const item = reservation(lease);
  const prepared = await reserve(db, item);
  if (prepared.status !== 200) return prepared;
  if (signal?.aborted) return { status: 503 };
  return activate(db, item);
}
