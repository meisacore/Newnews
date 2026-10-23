// A fixed fictional quote currency, never a live ETH price or blockchain balance.
export const SIM_ETH_USD = 3000;
export const toUsd = (value, unit) =>
  Number(value) * (unit === "ETH" ? SIM_ETH_USD : 1);
export const fromUsd = (value, unit) =>
  Number(value) / (unit === "ETH" ? SIM_ETH_USD : 1);
export function formatMoney(value, unit = "USD", compact = false) {
  const n = fromUsd(value || 0, unit);
  if (unit === "ETH" && n !== 0 && Math.abs(n) < 1e-12)
    return n.toExponential(2) + " ETH";
  if (unit === "ETH")
    return (
      new Intl.NumberFormat("en-US", {
        maximumFractionDigits: Math.abs(n) < 0.01 ? 12 : 6,
      }).format(n) + " ETH"
    );
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: compact ? "compact" : "standard",
    maximumFractionDigits: compact ? 1 : Math.abs(n) < 1 ? 10 : 2,
  }).format(n);
}
