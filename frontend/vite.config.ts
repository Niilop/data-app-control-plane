import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Only a server-side proxy target: root .env and its credentials are never loaded.
const target = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";
export default defineConfig({
  plugins: [react()],
  envDir: false,
  server: {
    port: 5173,
    strictPort: true,
    proxy: Object.fromEntries(
      ["/api", "/auth", "/health", "/ready"].map((path) => [
        path,
        { target, changeOrigin: false },
      ]),
    ),
  },
});
