import { defineConfig } from "@playwright/test";

/** 真实源码CSS的廉价布局夹具；不启动Next、OIDC或业务服务，不代替纵向验收。 */
export default defineConfig({
  testDir: "./tests/ui",
  testMatch: "mobile-navigation.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 10000,
  reporter: "list",
  outputDir: "artifacts/test-results/layout",
  use: { launchOptions: { channel: "msedge" }, trace: "off", screenshot: "off", video: "off" },
});
