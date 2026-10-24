import appConfig from "../app-config.json";
import { defineConfig, loadEnv } from "vite";
import { fileURLToPath } from "node:url";
export default defineConfig(({ mode }) => {
  const env = {
    ...loadEnv(mode, fileURLToPath(new URL(".", import.meta.url)), "VITE_"),
    ...process.env,
  };
  const appId = env.VITE_PRIVY_APP_ID ?? appConfig.privy_app_id;
  return {
    plugins: [
      {
        name: "norx-clean-routes",
        configureServer(server) {
          server.middlewares.use(marketPages);
        },
        configurePreviewServer(server) {
          server.middlewares.use(marketPages);
        },
      },
    ],
    define: { "import.meta.env.VITE_PRIVY_APP_ID": JSON.stringify(appId) },
    resolve: {
      alias: {
        "@norx/auth-root": fileURLToPath(
          new URL(
            appId ? "./src/PrivyRoot.jsx" : "./src/LocalRoot.jsx",
            import.meta.url,
          ),
        ),
      },
    },
    server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
    build: {
      rollupOptions: {
        input: {
          welcome: fileURLToPath(new URL("./index.html", import.meta.url)),
          market: fileURLToPath(new URL("./market.html", import.meta.url)),
        },
      },
    },
  };
});

function marketPages(req, res, next) {
  const path = (req.url || "").split("?")[0];
  if (
    /^\/(?:pulse|discover|trade(?:\/[^/]+)?|portfolio|agents)\/?$/.test(path) ||
    path === "/market"
  )
    req.url = "/market.html";
  next();
}
