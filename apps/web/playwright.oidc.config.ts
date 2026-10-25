import { defineConfig } from "@playwright/test";
/** 独立真实 OIDC/BFF 验收；环境由 Master 受控启动，禁止网络跟踪/认证截图。 */
export default defineConfig({ testDir: "./tests/oidc", workers: 1, reporter: "list", outputDir: "artifacts/test-results/oidc", timeout: 60000, use: { baseURL: process.env.PLATFORM_TEST_ORIGIN ?? "http://localhost:15100", launchOptions: { channel: "msedge" }, trace: "off", screenshot: "off", video: "off" } });
