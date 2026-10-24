import { PublicCache } from "./publicCache";
import { requestPublic } from "./requestJson";
const cache = new PublicCache();
const ports = new Set();
self.onconnect = (event) => {
  const port = event.ports[0];
  ports.add(port);
  port.onmessage = async ({ data }) => {
    const { id, world, path, type } = data;
    if (type === "close") {
      ports.delete(port);
      port.close();
      return;
    }
    if (type === "invalidate") {
      cache.invalidate(world);
      for (const listener of ports)
        if (listener !== port) listener.postMessage({ type: "changed", world });
      port.postMessage({ id, data: true });
      return;
    }
    try {
      const result = await cache.get(world, path, () =>
        requestPublic(path, world),
      );
      port.postMessage({ id, data: result });
    } catch (error) {
      port.postMessage({ id, error: error.message });
    }
  };
  port.start();
};
