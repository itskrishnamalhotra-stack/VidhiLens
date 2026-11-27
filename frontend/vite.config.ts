import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: process.env.LEGALAI_DEV_API_TARGET ? {
      "/test-api": {
        target: process.env.LEGALAI_DEV_API_TARGET,
        changeOrigin: true,
        rewrite: (path: string) => path.replace(/^\/test-api/, ""),
      },
    } : undefined,
  },
  preview: { port: 4173 },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
  },
});
