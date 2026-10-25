import { expect, test } from "@playwright/test";
/** 收口复验可显式隔离截图目录，默认保留原阶段入口。 */
const screenshots = process.env.PLATFORM_SCREENSHOT_DIR ?? "../../docs/evidence/G1-WAVE2/FE/screenshots";
/** 在框架生成error-context前移除异常详情，失败状态和固定步骤仍保留。 */
test.afterEach(async ({ page }, testInfo) => {
  void page;
  for (const error of testInfo.errors) {
    for (const key of Object.keys(error)) Reflect.deleteProperty(error, key);
  }
});
test.beforeEach(async () => {
  if (process.env.PLATFORM_OIDC_PRIVACY_PROBE === "1") throw new Error("SYNTHETIC_PRIVACY_PROBE");
});
/** 记录固定验收阶段，不附请求或身份材料。 */
function step(name: string) { test.info().annotations.push({ type: "safe-step", description: name }); }
/** 密码仅来自本次隔离测试进程环境，禁止写入结果、截图和网络trace。 */
async function signIn(page: import("@playwright/test").Page, user: string, password: string) {
  step("anonymous-redirect");
  await page.goto("/");
  await expect(page).toHaveURL(/localhost:18080/);
  step("credential-input");
  await page.locator("#username").fill(user);
  await page.locator("#password").fill(password);
  step("login-callback");
  await page.locator("#kc-login").click();
  await expect(page.getByRole("heading", { name: "平台资源", exact: true })).toBeVisible();
  step("browser-session-boundary");
  const session = (await page.context().cookies()).find(cookie => cookie.name === ".OntologyPlatform.Session");
  expect(session?.httpOnly).toBe(true);
  expect(session?.sameSite).toBe("Lax");
  expect(await page.evaluate(() => document.cookie.includes(".OntologyPlatform.Session"))).toBe(false);
  expect(await page.evaluate(() => Object.keys(localStorage).every(key => key === "ontology-theme") && sessionStorage.length === 0)).toBe(true);
}
test("真实匿名→Keycloak→受限资源→角色拒绝→安全注销", async ({ page }) => {
  const password = process.env.WAVE2_VIEWER_PASSWORD;
  if (!password) throw new Error("NOT_RUN: 需Master提供本次隔离viewer身份的运行时配置");
  await signIn(page, "wave2-viewer-a", password);
  step("allowed-resource");
  const legacyTarget = await page.getByText("site-a", { exact: true }).first().evaluate(element => element.tagName);
  test.info().annotations.push({ type: "safe-target", description: legacyTarget === "OPTION" ? "OPTION" : "OTHER" });
  const resourceResponse = await page.request.get("/api/v1/platform/resources");
  test.info().annotations.push({ type: "safe-resource-status", description: String(resourceResponse.status()) });
  expect(resourceResponse.status()).toBe(200);
  const resourceList = await resourceResponse.json();
  expect(resourceList.items.length).toBeGreaterThan(0);
  expect(resourceList.items.every((item: { siteId: string }) => item.siteId === "site-a")).toBe(true);
  await expect(page.getByRole("cell").filter({ hasText: "site-a" }).first()).toBeVisible();
  await page.screenshot({ path: `${screenshots}/oidc-viewer.png`, fullPage: true, animations: "disabled" });
  step("cross-site-denied");
  const denied = await page.request.get("/api/v1/platform/resources?siteId=site-b");
  expect(denied.status()).toBe(403);
  step("audit-denied");
  await page.getByRole("button", { name: "访问审计" }).click();
  await expect(page.getByRole("heading", { name: "当前身份无权访问" })).toBeVisible();
  step("logout");
  await page.getByRole("button", { name: "安全退出" }).click();
  await expect(page.getByRole("heading", { name: "已安全退出" })).toBeVisible();
  step("logged-out-401");
  expect((await page.request.get("/api/v1/platform/me")).status()).toBe(401);
});
test("真实已认证无角色身份展示403", async ({ page }) => {
  const password = process.env.WAVE2_NO_ROLE_PASSWORD;
  if (!password) throw new Error("NOT_RUN: 需Master提供本次隔离no-role身份的运行时配置");
  await signIn(page, "wave2-no-role-a", password);
  step("role-denied");
  await expect(page.getByRole("heading", { name: "当前身份无权访问" })).toBeVisible();
  step("logout");
  await page.getByRole("button", { name: "安全退出" }).click();
  await expect(page.getByRole("heading", { name: "已安全退出" })).toBeVisible();
  step("logged-out-401");
  expect((await page.request.get("/api/v1/platform/me")).status()).toBe(401);
});
