import test from "node:test";
import assert from "node:assert/strict";
import { databaseFailure, logFailure } from "../src/diagnostics.js";
import { errorResponse } from "../src/index.js";

test("generic driver errors become actionable categories without logging secrets", async (t) => {
  const secret = "postgresql://private-user:VERY-SECRET@example.com/postgres";
  const cases = [
    [
      new Error("Connection terminated due to connection timeout " + secret),
      "database_connection_timeout",
    ],
    [new Error("self-signed certificate " + secret), "database_tls"],
    [
      Object.assign(new Error("secret: " + secret), { code: "28P01" }),
      "database_authentication",
    ],
    [
      Object.assign(new Error("secret: " + secret), { code: "42P01" }),
      "database_setup",
    ],
    [new Error("Socket operation not supported " + secret), "database_runtime"],
    [new Error(secret), "unknown"],
    [
      new Error("outer", {
        cause: Object.assign(new Error(secret), { code: "ENOTFOUND" }),
      }),
      "database_dns",
    ],
  ];
  const logs = [];
  t.mock.method(console, "error", (...args) => logs.push(args));
  for (const [error, category] of cases) {
    error.norxStage = "connect";
    const result = databaseFailure(error);
    assert.equal(result.category, category);
    assert.equal(result.stage, "connect");
    logFailure("NORX API failed", error, "balanced");
    const response = errorResponse(error);
    assert.equal(response.status, 503);
    assert.ok(!(await response.text()).includes("VERY-SECRET"));
  }
  assert.ok(!JSON.stringify(logs).includes("VERY-SECRET"));
  assert.ok(!JSON.stringify(logs).includes("private-user"));
});
