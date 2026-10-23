import React, { lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { PublicApp } from "./App";
import { CurrencyProvider } from "./Currency";
const PrivyRoot = lazy(() => import("@norx/auth-root"));
const id = import.meta.env.VITE_PRIVY_APP_ID;
class StartupBoundary extends React.Component {
  state = { error: null };
  static getDerivedStateFromError(error) {
    return { error };
  }
  render() {
    if (this.state.error)
      return (
        <div id="startup">
          <div className="startup-card">
            <div className="startup-brand">
              NOR<span>X</span>
            </div>
            <h1>The exchange could not start.</h1>
            <p id="startup-details">{this.state.error.message}</p>
            <a className="startup-reload" href="market.html">
              Reload exchange
            </a>
          </div>
        </div>
      );
    return this.props.children;
  }
}
createRoot(document.getElementById("root")).render(
  <StartupBoundary>
    <CurrencyProvider>
      {id ? (
        <Suspense
          fallback={
            <div className="app loading-world">Opening your world…</div>
          }
        >
          <PrivyRoot id={id} />
        </Suspense>
      ) : (
        <PublicApp />
      )}
    </CurrencyProvider>
  </StartupBoundary>,
);
