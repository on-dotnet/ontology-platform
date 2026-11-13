import { defineConfig } from "vitest/config";
export default defineConfig({
  cacheDir: "../../artifacts/workflow/G4-M2-DORIS-01/runtime-cache/vite",
  test: {
    fsModuleCachePath: "../../artifacts/workflow/G4-M2-DORIS-01/runtime-cache/modules",
    environment: "node",
    include: ["src/**/*.test.ts"],
    reporters: ["default", "json"],
    outputFile: { json: "../../artifacts/workflow/G4-M2-DORIS-01/ui-report.json" },
  },
});
