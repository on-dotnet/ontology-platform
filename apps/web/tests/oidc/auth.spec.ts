import { expect, test } from "@playwright/test";
/** 密码仅来自本次隔离测试进程环境，禁止写入结果、截图和网络trace。 */
async function signIn(page: import("@playwright/test").Page, user: string, password: string) {
  await page.goto("/");
  await expect(page).toHaveURL(/localhost:18080/);
  await page.locator("#username").fill(user);
  await page.locator("#password").fill(password);
  await page.locator("#kc-login").click();
  await expect(page.getByRole("heading", { name: "平台资源", exact: true })).toBeVisible();
}
test("真实匿名→Keycloak→受限资源→角色拒绝→安全注销", async ({ page }) => {
  const password = process.env.WAVE2_VIEWER_PASSWORD;
  if (!password) throw new Error("NOT_RUN: 需Master提供本次隔离viewer身份的运行时配置");
  await signIn(page, "wave2-viewer-a", password);
  await expect(page.getByText("site-a", { exact: true }).first()).toBeVisible();
  const denied = await page.request.get("/api/v1/platform/resources?siteId=site-b");
  expect(denied.status()).toBe(403);
  await page.getByRole("button", { name: "访问审计" }).click();
  await expect(page.getByRole("heading", { name: "当前身份无权访问" })).toBeVisible();
  await page.getByRole("button", { name: "安全退出" }).click();
  await expect(page.getByRole("heading", { name: "已安全退出" })).toBeVisible();
  expect((await page.request.get("/api/v1/platform/me")).status()).toBe(401);
});
test("真实已认证无角色身份展示403", async ({ page }) => {
  const password = process.env.WAVE2_NO_ROLE_PASSWORD;
  if (!password) throw new Error("NOT_RUN: 需Master提供本次隔离no-role身份的运行时配置");
  await signIn(page, "wave2-no-role-a", password);
  await expect(page.getByRole("heading", { name: "当前身份无权访问" })).toBeVisible();
  await page.getByRole("button", { name: "安全退出" }).click();
  await expect(page.getByRole("heading", { name: "已安全退出" })).toBeVisible();
});
