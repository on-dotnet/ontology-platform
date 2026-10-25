import { expect, test } from "@playwright/test";
const resources = { items: [{ id: "platform-site-a", name: "厂区 A · 开发合成资源", organizationId: "org-demo", siteId: "site-a", status: "SyntheticDevelopment" }], auditId: "ui-test-audit", traceId: "ui-test-trace" };
test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/platform/resources*", route => route.fulfill({ json: resources }));
});
test("1280布局、键盘详情、浅色持久化和Console", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 1000 });
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "平台资源", exact: true })).toBeVisible();
  await expect(page.getByText("厂区 A · 开发合成资源", { exact: true })).toBeVisible();
  await expect(page.getByText("ui-test-trace", { exact: true })).toBeVisible();
  await page.screenshot({ path: "../../docs/evidence/G1-WAVE2/FE/screenshots/1280-dark.png", fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: "查看详情" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "查看详情" })).toBeFocused();
  await page.getByRole("button", { name: "切换深浅主题" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "../../docs/evidence/G1-WAVE2/FE/screenshots/1280-light.png", fullPage: true, animations: "disabled" });
  expect(errors).toEqual([]);
});
test("宽屏、移动导航、授权范围与搜索空状态", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await expect(page.getByText("厂区 A · 开发合成资源", { exact: true })).toBeVisible();
  await page.screenshot({ path: "../../docs/evidence/G1-WAVE2/FE/screenshots/1920-dark.png", fullPage: true, animations: "disabled" });
  await page.getByRole("textbox", { name: "搜索平台资源" }).fill("不存在的资源");
  await expect(page.getByRole("heading", { name: "没有匹配的资源" })).toBeVisible();
  await page.getByRole("button", { name: "授权范围" }).click();
  await expect(page.getByRole("heading", { name: "当前身份与访问边界" })).toBeVisible();
  await expect(page.getByText("platform.viewer", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("button", { name: "平台资源", exact: true }).click();
  await expect(page.getByRole("heading", { name: "平台资源", exact: true })).toBeVisible();
  await expect(page.getByText("厂区 A · 开发合成资源", { exact: true })).toBeVisible();
  await page.screenshot({ path: "../../docs/evidence/G1-WAVE2/FE/screenshots/390-dark.png", fullPage: true, animations: "disabled" });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
test("加载中、403、网络错误、空集合和会话过期各自准确", async ({ page }) => {
  let release: (() => void) | undefined;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/platform/resources*", async route => { await gate; await route.fulfill({ status: 403, json: { status: 403, code: "forbidden", traceId: "denied-trace" } }); });
  await page.goto("/");
  await expect(page.getByRole("status")).toBeVisible();
  release!();
  await expect(page.getByRole("heading", { name: "当前身份无权访问" })).toBeVisible();
  await page.route("**/api/v1/platform/resources*", route => route.abort("failed"));
  await page.getByRole("button", { name: "刷新数据" }).click();
  await expect(page.getByRole("heading", { name: "暂时无法读取数据" })).toBeVisible();
  await page.route("**/api/v1/platform/resources*", route => route.fulfill({ json: { ...resources, items: [] } }));
  await page.getByRole("button", { name: "重新读取" }).click();
  await expect(page.getByRole("heading", { name: "当前范围内暂无资源" })).toBeVisible();
  await page.route("**/api/v1/platform/resources*", route => route.fulfill({ status: 401, json: { status: 401, code: "unauthenticated" } }));
  await page.getByRole("button", { name: "刷新数据" }).click();
  await expect(page.getByRole("link", { name: "重新登录" })).toHaveAttribute("href", "/auth/login?returnUrl=/");
});
test("审计拒绝和公开注销面板", async ({ page }) => {
  await page.route("**/api/v1/platform/audit*", route => route.fulfill({ status: 403, json: { status: 403, code: "forbidden" } }));
  await page.goto("/");
  await page.getByRole("button", { name: "访问审计" }).click();
  await expect(page.getByRole("heading", { name: "当前身份无权访问" })).toBeVisible();
  await page.goto("/signed-out");
  await expect(page.getByRole("heading", { name: "已安全退出" })).toBeVisible();
  await expect(page.getByRole("link", { name: /使用组织身份登录/ })).toHaveAttribute("href", "/auth/login?returnUrl=/");
});

test("390关闭导航跳过屏外Tab且响应式桌面菜单可用", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  // 原生AX树反映读屏可见性；Playwright角色选择器本身不排除inert元素。
  const accessibility = await page.context().newCDPSession(page);
  async function navigationIsExposed() {
    const { nodes } = await accessibility.send("Accessibility.getFullAXTree");
    return nodes.some(node => !node.ignored && node.role?.value === "complementary" && node.name?.value === "主导航");
  }
  await expect(page.getByRole("heading", { name: "平台资源", exact: true })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "跳到主内容" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "打开导航" })).toBeFocused();
  await expect.poll(navigationIsExposed).toBe(false);
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect.poll(navigationIsExposed).toBe(true);
  await page.getByRole("button", { name: "授权范围", exact: true }).click();
  await expect(page.getByRole("heading", { name: "当前身份与访问边界" })).toBeVisible();
  await expect.poll(navigationIsExposed).toBe(false);
  await page.setViewportSize({ width: 1280, height: 1000 });
  await expect.poll(navigationIsExposed).toBe(true);
  await page.getByRole("button", { name: "平台资源", exact: true }).focus();
  await expect(page.getByRole("button", { name: "平台资源", exact: true })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "平台资源", exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(navigationIsExposed).toBe(false);
});
