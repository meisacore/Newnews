export const BUY_PRESETS = [25, 50, 250];
export function filterPulseRows(rows, query, filters, now) {
  const words = query
    .toLowerCase()
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return rows.filter((c) => {
    if (
      words.length &&
      !words.some((word) =>
        (c.name + " " + c.symbol + " " + c.id).toLowerCase().includes(word),
      )
    )
      return false;
    const bounds = [
      ["minCap", c.market_cap, "min"],
      ["maxCap", c.market_cap, "max"],
      ["minVolume", c.volume_24h, "min"],
      ["minHolders", c.holders, "min"],
      [
        "maxAge",
        Number.isFinite(c.created_at)
          ? Math.max(0, now - c.created_at) / 60
          : undefined,
        "max",
      ],
    ];
    return bounds.every(([key, value, kind]) => {
      const raw = filters[key];
      if (raw == null || raw === "") return true;
      const bound = Number(raw);
      return (
        Number.isFinite(value) &&
        Number.isFinite(bound) &&
        bound >= 0 &&
        (kind === "min" ? value >= bound : value <= bound)
      );
    });
  });
}
export function sortPulseRows(rows, sort) {
  return [...rows].sort((a, b) =>
    sort === "volume"
      ? b.volume_24h - a.volume_24h
      : sort === "cap"
        ? b.market_cap - a.market_cap
        : b.created_at - a.created_at || b.id.localeCompare(a.id),
  );
}
