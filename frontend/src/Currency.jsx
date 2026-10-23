import React, { createContext, useContext, useState } from "react";
import { SIM_ETH_USD, fromUsd, toUsd, formatMoney } from "./money";
const Currency = createContext(null);
export function CurrencyProvider({ children }) {
  const [unit, setUnit] = useState(() => {
    try {
      return localStorage.getItem("norx.currency") === "ETH" ? "ETH" : "USD";
    } catch {
      return "USD";
    }
  });
  function choose(value) {
    setUnit(value);
    try {
      localStorage.setItem("norx.currency", value);
    } catch {}
  }
  return (
    <Currency.Provider
      value={{
        unit,
        setUnit: choose,
        rate: SIM_ETH_USD,
        format: (n) => formatMoney(n, unit),
        compact: (n) => formatMoney(n, unit, true),
        fromUsd: (n) => fromUsd(n, unit),
        toUsd: (n) => toUsd(n, unit),
      }}
    >
      {children}
    </Currency.Provider>
  );
}
export const useCurrency = () => useContext(Currency);
