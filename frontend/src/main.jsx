import React, { lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { PublicApp } from "./App";
const PrivyRoot = lazy(() => import("./PrivyRoot"));
const id = import.meta.env.VITE_PRIVY_APP_ID;
createRoot(document.getElementById("root")).render(
  id ? (
    <Suspense
      fallback={<div className="app loading-world">Opening your world…</div>}
    >
      <PrivyRoot id={id} />
    </Suspense>
  ) : (
    <PublicApp />
  ),
);
