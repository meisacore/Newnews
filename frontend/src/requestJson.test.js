import test from "node:test";
import assert from "node:assert/strict";
import { requestJson } from "./requestJson.js";
test("portfolio retries retain HTTP status and Retry-After, including non-JSON failures", async (t) => {
  t.mock.method(globalThis, "fetch", async () =>
    Response.json(
      { detail: "The market is busy" },
      { status: 503, headers: { "Retry-After": "2" } },
    ),
  );
  await assert.rejects(
    requestJson("me", "balanced", { token: "test-token" }),
    (e) =>
      e.status === 503 &&
      e.retryAfterMs === 2000 &&
      e.message === "The market is busy",
  );
  globalThis.fetch = async () =>
    new Response("Internal Server Error", { status: 500 });
  await assert.rejects(
    requestJson("me", "balanced"),
    (e) => e.status === 500 && e.retryAfterMs === 0,
  );
  globalThis.fetch = async () =>
    Response.json({ detail: "Invalid session" }, { status: 401 });
  await assert.rejects(requestJson("me", "balanced"), (e) => e.status === 401);
});
