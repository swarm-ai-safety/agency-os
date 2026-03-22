import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["app/**/*.test.{ts,tsx}"],
    // Coverage artifact writes can flake on macOS with parallel workers.
    // Keep coverage tests single-threaded and avoid fork-worker startup flakiness.
    maxWorkers: 1,
    fileParallelism: false,
    pool: "threads",
    coverage: {
      provider: "v8",
      // Managed by package.json test:coverage to avoid temp-dir cleanup races.
      clean: false,
      reporter: ["text", "lcov", "json-summary"],
      include: ["app/**/*.{ts,tsx}"],
      exclude: ["app/api/**", "app/**/layout.tsx", "app/icon.png"],
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});
