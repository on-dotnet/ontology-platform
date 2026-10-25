import { defineConfig } from "@playwright/test";
// 安装版本的Playwright以此关闭失败页面快照；异常详情由suite钩子在落盘前移除。
process.env.PLAYWRIGHT_NO_COPY_PROMPT = "1";
/** 独立真实 OIDC/BFF 验收；环境由 Master 受控启动，禁止网络跟踪/认证截图。 */
export default defineConfig({ testDir: "./tests/oidc", workers: 1, reporter: [["./tests/oidc/safe-reporter.ts"]], outputDir: "artifacts/test-results/oidc", timeout: 60000, use: { baseURL: process.env.PLATFORM_TEST_ORIGIN ?? "http://localhost:15100", launchOptions: { channel: "msedge" }, trace: "off", screenshot: "off", video: "off" } });
