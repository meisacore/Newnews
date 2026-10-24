import test from "node:test";
import assert from "node:assert/strict";
import { visiblePolling } from "./visiblePolling.js";
function harness(hidden = false) {
  const doc = new EventTarget();
  doc.hidden = hidden;
  const timers = new Map();
  let id = 0;
  return {
    doc,
    timers,
    options: {
      document: doc,
      setTimer: (fn) => {
        timers.set(++id, fn);
        return id;
      },
      clearTimer: (key) => timers.delete(key),
    },
    tick() {
      const [key, fn] = timers.entries().next().value;
      timers.delete(key);
      fn();
    },
    visibility(value) {
      doc.hidden = value;
      doc.dispatchEvent(new Event("visibilitychange"));
    },
  };
}
const flush = async () => {
  await Promise.resolve();
  await Promise.resolve();
};
test("hidden tabs do not poll; returning triggers a refresh; cleanup stops timers", async () => {
  const h = harness(true);
  let calls = 0;
  const p = visiblePolling(async () => calls++, 10000, h.options);
  await flush();
  assert.equal(calls, 0);
  assert.equal(h.timers.size, 0);
  h.visibility(false);
  await flush();
  assert.equal(calls, 1);
  assert.equal(h.timers.size, 1);
  h.visibility(true);
  assert.equal(h.timers.size, 0);
  h.visibility(false);
  await flush();
  assert.equal(calls, 2);
  p.stop();
  assert.equal(h.timers.size, 0);
  h.visibility(false);
  assert.equal(calls, 2);
});
test("a slow response finishes before another request starts", async () => {
  const h = harness();
  let calls = 0,
    finish;
  const p = visiblePolling(
    () => {
      calls++;
      return new Promise((resolve) => (finish = resolve));
    },
    10000,
    h.options,
  );
  assert.equal(calls, 1);
  p.refresh();
  assert.equal(calls, 1);
  finish();
  await flush();
  assert.equal(calls, 2);
  assert.equal(h.timers.size, 0);
  p.stop();
  finish();
  await flush();
  assert.equal(h.timers.size, 0);
});

test("temporary retry delay returns to normal and still pauses while hidden", async () => {
  const h = harness();
  const delays = [];
  let calls = 0;
  const p = visiblePolling(
    async () => {
      calls++;
    },
    60000,
    {
      ...h.options,
      nextDelay: () => (calls === 1 ? 2000 : 60000),
      setTimer: (fn, delay) => {
        delays.push(delay);
        return h.options.setTimer(fn, delay);
      },
    },
  );
  await flush();
  assert.deepEqual(delays, [2000]);
  h.tick();
  await flush();
  assert.deepEqual(delays, [2000, 60000]);
  h.visibility(true);
  assert.equal(h.timers.size, 0);
  h.visibility(false);
  await flush();
  assert.equal(calls, 3);
  p.stop();
  assert.equal(h.timers.size, 0);
});
