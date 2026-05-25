import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxyTarget = process.env.SCISTUDIO_API_PROXY ?? "http://localhost:8000";
const wsProxyTarget = apiProxyTarget.replace(/^http/, "ws");

export default defineConfig({
  base: "./",
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      // PTY WebSocket — must match before the generic /api rule so the
      // upgrade request is routed through a proxy with ws:true.
      "/api/ai/pty": {
        target: wsProxyTarget,
        ws: true,
        changeOrigin: true,
      },
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      "/ws": {
        target: wsProxyTarget,
        ws: true,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    exclude: ["e2e/**", "node_modules/**", "dist/**"],
    setupFiles: "./vitest.setup.ts",
    css: true,
  },
});
