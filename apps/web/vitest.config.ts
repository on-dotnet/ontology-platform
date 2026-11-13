import { defineConfig } from "vitest/config";
/** 仅允许当前两个M2执行入口，报告与缓存不跨任务覆盖。 */
const task = process.env.G4_TEST_TASK ?? "G4-M2-DORIS-01";
if (!["G4-M2-DORIS-01", "G4-M2-ORACLE-01"].includes(task)) throw new Error("Unsupported test task");
const directory = `../../artifacts/workflow/${task}`;
export default defineConfig({
  cacheDir: `${directory}/runtime-cache/vite`,
  test: {
    fsModuleCachePath: `${directory}/runtime-cache/modules`,
    environment: "node",
    include: ["src/**/*.test.ts"],
    reporters: ["default", "json"],
    outputFile: { json: `${directory}/ui-report.json` },
  },
});
