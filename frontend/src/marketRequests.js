import { PublicCache } from "./publicCache";
import { requestPublic } from "./requestJson";
const fallback = new PublicCache();
let worker;
const pending = new Map();
let sequence = 0;
function sharedWorker() {
  if (worker !== undefined) return worker;
  worker = null;
  if (typeof SharedWorker === "undefined") return null;
  try {
    worker = new SharedWorker(new URL("./market.worker.js", import.meta.url), {
      type: "module",
      name: "norx-public-market",
    });
    worker.port.onmessage = ({ data }) => {
      if (data.type === "changed") {
        window.dispatchEvent(
          new CustomEvent("norx:portfolio-refresh", {
            detail: { world: data.world },
          }),
        );
        return;
      }
      const waiter = pending.get(data.id);
      if (!waiter) return;
      pending.delete(data.id);
      clearTimeout(waiter.timer);
      data.error ? waiter.reject(Error(data.error)) : waiter.resolve(data.data);
    };
    worker.onerror = () => {
      worker = null;
      for (const waiter of pending.values()) {
        clearTimeout(waiter.timer);
        waiter.reject(
          Error("Shared market connection interrupted. Retrying shortly."),
        );
      }
      pending.clear();
    };
    worker.port.start();
    window.addEventListener("pagehide", (event) => {
      if (!event.persisted) worker?.port.postMessage({ type: "close" });
    });
  } catch {
    worker = null;
  }
  return worker;
}
function message(data) {
  const current = sharedWorker();
  if (!current) return null;
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => {
      pending.delete(id);
      worker = null;
      reject(Error("Market update took too long. Retrying shortly."));
    }, 30000);
    pending.set(id, { resolve, reject, timer });
    current.port.postMessage({ id, ...data });
  });
}
export function publicMarketRequest(path, world) {
  const local = () =>
    fallback.get(world, path, () => requestPublic(path, world));
  const shared = message({ type: "get", path, world });
  return shared
    ? shared.catch((error) => {
        if (!worker) return local();
        throw error;
      })
    : local();
}

export async function invalidatePublicMarket(world) {
  fallback.invalidate(world);
  const sent = message({ type: "invalidate", world });
  if (sent) {
    try {
      await sent;
    } catch {
      worker = null;
    } // A completed trade must not fail because UI invalidation failed.
  }
}
