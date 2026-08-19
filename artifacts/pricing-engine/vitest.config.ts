import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  // Zelfde JSX-transform als Vite's react-plugin, zodat tests modules met
  // .tsx-imports (bijv. de route-registry) kunnen laden.
  esbuild: { jsx: "automatic" },
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
