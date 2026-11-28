// Sites grants this app to exactly one owner, so the 160-owner budget also
// enforces the historical 180-global budget. D1 batches commit atomically.
const clean = "DELETE FROM lab_admission WHERE active=0 AND started<=unixepoch()-60";
const admit = `INSERT INTO lab_admission (lease,started,active)
  SELECT ?,unixepoch(),1
  WHERE (SELECT count(*) FROM lab_admission WHERE active=1)<4
    AND (SELECT count(*) FROM lab_admission WHERE started>unixepoch()-60)<160
  ON CONFLICT(lease) DO NOTHING`;
const state = "SELECT active FROM lab_admission WHERE lease=?";
const finish = "UPDATE lab_admission SET active=0 WHERE lease=? AND active=1";

export async function acquire(db, lease) {
  if (!db) return { status: 503 };
  const admission = () => [db.prepare(clean), db.prepare(admit).bind(lease)];
  let granted;
  try {
    const [, result] = await db.batch(admission());
    if (!result.success) throw new Error("D1 admission unavailable");
    granted = result.meta.changes === 1;
  } catch {
    // Retry with the same lease. A committed insert whose response was lost
    // remains the same slot. Read it in the same transaction as the retry.
    try {
      const [, , result] = await db.batch([...admission(), db.prepare(state).bind(lease)]);
      if (!result.success) return { status: 503 };
      granted = result.results[0]?.active === 1;
    } catch {
      return { status: 503 };
    }
  }
  if (!granted) return { status: 429 };
  return {
    status: 200,
    async release() {
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          const result = await db.prepare(finish).bind(lease).run();
          // A committed update that lost its response may match zero rows on retry.
          // Successful execution still guarantees that this lease is no longer active.
          if (result.success) return true;
        } catch {
          // Once both attempts fail the caller returns 503 with the lease unchanged.
        }
      }
      return false;
    },
  };
}
