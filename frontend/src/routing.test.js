import test from "node:test";
import assert from "node:assert/strict";
import { readRoute, routePath, isMarketPath } from "./routing.js";

test("clean paths and legacy bookmarks resolve to the same market views", () => {
  for (const view of ["pulse", "discover", "trade", "portfolio", "agents"]) {
    assert.deepEqual(readRoute({ pathname: "/" + view, hash: "" }), { view });
    assert.deepEqual(
      readRoute({ pathname: "/market.html", hash: "#" + view }),
      { view },
    );
    assert.equal(routePath({ view }), "/" + view);
  }
  assert.deepEqual(readRoute({ pathname: "/trade/coin-00000001", hash: "" }), {
    view: "coin",
    coin: "coin-00000001",
  });
  assert.deepEqual(
    readRoute({ pathname: "/market.html", hash: "#coin/frog" }),
    { view: "coin", coin: "frog" },
  );
  assert.equal(
    routePath({ view: "coin", coin: "space token" }),
    "/trade/space%20token",
  );
  assert.deepEqual(readRoute({ pathname: "/trade/%invalid", hash: "" }), {
    view: "trade",
  });
  assert.equal(isMarketPath("/trade/frog"), true);
  for (const path of [
    "/api/state",
    "/assets/missing.js",
    "/favicon.svg",
    "/trade/frog/unknown",
  ])
    assert.equal(isMarketPath(path), false);
});
