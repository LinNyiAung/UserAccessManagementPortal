import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the portal UI and the API share one origin (this dev server),
// so the SSO session cookie and the OIDC endpoints live under the same URL.
// Port 8100: 8000 belongs to the Logistics Price Calculator's API.
const backend = "http://127.0.0.1:8100";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": backend,
      "/oauth": backend,
      "/.well-known": backend,
    },
  },
});
