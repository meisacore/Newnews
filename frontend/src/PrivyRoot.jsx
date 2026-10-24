import React from "react";
import { PrivyProvider, usePrivy } from "@privy-io/react-auth";
import { App } from "./App";
function PrivyApp() {
  const p = usePrivy();
  return (
    <App
      auth={{
        ready: p.ready,
        authenticated: p.authenticated,
        login: p.login,
        logout: p.logout,
        getToken: p.getAccessToken,
      }}
    />
  );
}
export default function PrivyRoot({ id }) {
  return (
    <PrivyProvider
      appId={id}
      config={{
        loginMethods: ["email"],
        embeddedWallets: {
          ethereum: { createOnLogin: "off" },
          solana: { createOnLogin: "off" },
          showWalletUIs: false,
        },
        appearance: { theme: "dark", accentColor: "#c9b48c" },
      }}
    >
      <PrivyApp />
    </PrivyProvider>
  );
}
