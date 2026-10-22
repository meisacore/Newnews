import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
export default defineConfig({
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  build: {
    rollupOptions: {
      input: {
        welcome: fileURLToPath(new URL("./index.html", import.meta.url)),
        market: fileURLToPath(new URL("./market.html", import.meta.url)),
      },
    },
  },
});
