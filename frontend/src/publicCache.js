// Public market snapshots only: never accounts, tokens, quotes or trade requests.
export function isPublicMarketPath(path) {
  return /^(state(?:\?[^#]*)?|candles\/[^/?#]+(?:\?[^#]*)?)$/.test(path);
}
export class PublicCache {
  constructor({ ttl = 8000, capacity = 32, clock = Date.now } = {}) {
    this.ttl = ttl;
    this.capacity = capacity;
    this.clock = clock;
    this.values = new Map();
    this.pending = new Map();
    this.epochs = new Map();
  }
  invalidate(world) {
    this.epochs.set(world, (this.epochs.get(world) || 0) + 1);
    for (const [key, entry] of this.values)
      if (entry.world === world) this.values.delete(key);
  }
  async get(world, path, produce) {
    if (
      !["balanced", "bull", "bear", "mania"].includes(world) ||
      !isPublicMarketPath(path)
    )
      throw Error("Only public market requests can be shared");
    const epoch = this.epochs.get(world) || 0;
    const key = JSON.stringify([world, epoch, path]);
    const hit = this.values.get(key);
    if (hit && hit.expires > this.clock()) {
      this.values.delete(key);
      this.values.set(key, hit);
      return hit.data;
    }
    if (this.pending.has(key)) return this.pending.get(key);
    const promise = Promise.resolve()
      .then(produce)
      .then((data) => {
        if (epoch === (this.epochs.get(world) || 0)) {
          this.values.delete(key);
          this.values.set(key, {
            world,
            data,
            expires: this.clock() + this.ttl,
          });
          while (this.values.size > this.capacity)
            this.values.delete(this.values.keys().next().value);
        }
        return data;
      })
      .finally(() => this.pending.delete(key));
    this.pending.set(key, promise);
    return promise;
  }
}
