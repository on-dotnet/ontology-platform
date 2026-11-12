import { defineConfig } from "vitest/config";
export default defineConfig({
  cacheDir: "../../artifacts/workflow/G4-ENG-DELIVERY-002/runtime-cache/vite",
  test: {
    fsModuleCachePath: "../../artifacts/workflow/G4-ENG-DELIVERY-002/runtime-cache/modules",
    environment: "node",
    include: ["src/**/*.test.ts"],
    reporters: ["default", "json"],
    outputFile: { json: "../../artifacts/workflow/G4-ENG-DELIVERY-002/ui-report.json" },
  },
});
