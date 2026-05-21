import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendPort = process.env.SCISTUDIO_E2E_BACKEND_PORT ?? "8000";
const httpApiTarget = process.env.SCISTUDIO_API_TARGET ?? `http://127.0.0.1:${backendPort}`;
const wsApiTarget = process.env.SCISTUDIO_WS_TARGET ?? `ws://127.0.0.1:${backendPort}`;

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
        target: wsApiTarget,
        ws: true,
        changeOrigin: true,
      },
      "/api": {
        target: httpApiTarget,
        changeOrigin: true,
      },
      "/ws": {
        target: wsApiTarget,
        ws: true,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./vitest.setup.ts",
    css: true,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
