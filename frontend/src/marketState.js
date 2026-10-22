export function validateMarketState(data) {
  if (
    data?.api_version !== 3 ||
    !Array.isArray(data.coins) ||
    !Number.isFinite(data.next_launch_at) ||
    !Number.isFinite(data.server_time) ||
    !data.pulse_counts ||
    !data.simulation ||
    typeof data.simulation.running !== "boolean" ||
    !["new", "stretch", "migrated"].every((stage) =>
      Number.isInteger(data.pulse_counts[stage]),
    ) ||
    !data.coins.every((coin) =>
      ["new", "stretch", "migrated"].includes(coin.stage),
    )
  ) {
    throw new Error(
      "The backend is out of date. Stop it with Ctrl+C, update the project files, and restart the backend.",
    );
  }
  return data;
}
