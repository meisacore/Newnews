import { POLICIES, SCENARIOS, ApiError } from "./config.js";
import { withDatabase, one, commit } from "./database.js";
import { buildState } from "./state.js";

// At most one batch per ten seconds per active world, regardless of user count.
// Cron visits active worlds each minute. No catch-up launch flood after inactivity.
export async function advance(
  env,
  world,
  { visit = false, now = Math.floor(Date.now() / 1000) } = {},
) {
  return withDatabase(env, world, async (db, schema) => {
    const lock = await one(
      db,
      "SELECT pg_try_advisory_xact_lock(hashtext($1)) AS acquired",
      ["norx-write-" + schema],
    );
    if (!lock.acquired) return null;
    const control = await one(db, "SELECT * FROM cloud_runtime WHERE id=1");
    if (!control)
      throw new ApiError(503, "Cloudflare database setup is incomplete");
    if (visit) {
      const waking = Number(control.active_until) < now;
      // Throttle activity writes to once a minute. Cached requests need no writes.
      if (Number(control.active_until) < now + 60)
        await db.query("UPDATE cloud_runtime SET active_until=$1 WHERE id=1", [
          now + 120,
        ]);
      if (waking && control.snapshot) {
        await db.query("UPDATE meta SET value=$1 WHERE key='next_launch_at'", [
          String(now + 60),
        ]);
      }
    } else if (Number(control.active_until) < now) return null;
    if (Number(control.next_batch_at) > now && control.snapshot)
      return commit(db, control.snapshot);
    const owner = await one(
      db,
      "SELECT value FROM meta WHERE key='simulation_engine'",
    );
    if (owner?.value !== "cloudflare")
      throw new ApiError(
        503,
        "Activate the Cloudflare simulation using cloudflare/prepare.py --activate",
      );
    await db.query("SELECT norx_batch($1,$2::jsonb,$3::jsonb)", [
      now,
      JSON.stringify(SCENARIOS[world]),
      JSON.stringify(POLICIES),
    ]);
    const snapshot = await buildState(db, now);
    await db.query(
      "UPDATE cloud_runtime SET snapshot=$1::jsonb,snapshot_at=$2,next_batch_at=$3 WHERE id=1",
      [JSON.stringify(snapshot), now, now + 10],
    );
    return commit(db, snapshot);
  });
}
export async function readSnapshot(env, world) {
  return withDatabase(env, world, async (db) => {
    const r = await one(
      db,
      "SELECT snapshot,snapshot_at,next_batch_at,active_until FROM cloud_runtime WHERE id=1",
    );
    return r;
  });
}
export async function scheduled(env) {
  // Sequential worlds bound DB concurrency and avoid four large responses at once.
  for (const world of Object.keys(SCENARIOS)) {
    try {
      await advance(env, world);
    } catch (error) {
      console.error(
        "NORX scheduled batch failed",
        world,
        error.code || error.name,
      );
    }
  }
}
