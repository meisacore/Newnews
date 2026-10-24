import { POLICIES, SCENARIOS } from "./config.js";
import { withDatabase, one, commit } from "./database.js";
import { logFailure } from "./diagnostics.js";

// Aggregation and JSON assembly stay inside PostgreSQL. Only one boolean crosses
// the wire for a refresh, rather than thousands of rows and a full snapshot twice.
export async function advance(
  env,
  world,
  { visit = false, now = Math.floor(Date.now() / 1000) } = {},
) {
  return withDatabase(env, world, async (db) => {
    db.norxStage = "simulation_refresh";
    const result = await one(
      db,
      "SELECT norx_refresh($1,$2,$3::jsonb,$4::jsonb) AS ready",
      [now, visit, JSON.stringify(SCENARIOS[world]), JSON.stringify(POLICIES)],
    );
    return commit(db, result.ready);
  });
}
export async function readSnapshot(
  env,
  world,
  { selected = null, agents = false, now = Math.floor(Date.now() / 1000) } = {},
) {
  return withDatabase(env, world, async (db) => {
    db.norxStage = "snapshot_read";
    // Explicit text return: pg must not JSON.parse the large snapshot in Workers.
    return one(db, "SELECT * FROM norx_snapshot($1,$2,$3)", [
      now,
      selected,
      agents,
    ]);
  });
}
export async function scheduled(env) {
  for (const world of Object.keys(SCENARIOS)) {
    try {
      await advance(env, world);
    } catch (error) {
      logFailure("NORX scheduled batch failed", error, world);
    }
  }
}
