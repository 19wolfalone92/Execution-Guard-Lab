// Sites grants this app to exactly one owner, so the 160-owner budget also
// enforces the historical 180-global budget. D1 batches commit atomically.
const clean = "DELETE FROM lab_admission WHERE active=0 AND started<=unixepoch()-60";
const admit = `INSERT INTO lab_admission (lease,started,active)
  SELECT ?,unixepoch(),1
  WHERE (SELECT count(*) FROM lab_admission WHERE active=1)<4
    AND (SELECT count(*) FROM lab_admission WHERE started>unixepoch()-60)<160`;
const finish = "UPDATE lab_admission SET active=0 WHERE lease=? AND active=1";

export async function acquire(db, lease) {
  if (!db) return { status: 503 };
  try {
    const [, result] = await db.batch([db.prepare(clean), db.prepare(admit).bind(lease)]);
    if (result.meta.changes !== 1) return { status: 429 };
    return {
      status: 200,
      async release() {
        const result = await db.prepare(finish).bind(lease).run();
        return result.meta.changes === 1;
      },
    };
  } catch {
    return { status: 503 };
  }
}
