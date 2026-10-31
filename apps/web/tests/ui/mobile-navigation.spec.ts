import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";

/** 此隔离夹具验证真实源码CSS的布局/主题；不代替真实React、OIDC或M5纵向浏览器。 */
async function layoutFixture(page: Page, theme: "dark" | "light") {
  const css = (await Promise.all([
    "../../src/styles/globals.css", "../../src/features/ontology/workspace.css", "../../src/features/ontology/expression-tree.css",
  ].map(path => readFile(new URL(path, import.meta.url), "utf8")))).join("\n");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.setContent(`<style>${css}</style><div class="shell">
    <aside id="platform-navigation" class="sidebar" inert aria-label="主导航"><button class="nav-item">本体资产</button></aside>
    <div class="shell-body"><header class="topbar"><button class="icon-button mobile-menu" aria-label="打开导航">菜单</button></header>
      <main class="workspace-main"><div class="g2-workspace"><h1>本体资产与草稿</h1>
        <section class="g2-panel" aria-label="草稿高阶表达式"><div class="g2-tabs">
          <button class="button" aria-pressed="true">高阶表达式</button></div>
          <button class="button">刷新高阶表达式</button><p>source-preserved · read-only-structured</p>
        </section></div></main></div></div>`);
  await page.evaluate(async value => {
    document.documentElement.dataset.theme = value;
    // 读取计算样式以建立真实主题过渡，再等待它自然完成，禁止把中间帧当稳定按钮配色。
    getComputedStyle(document.querySelector(".button")!).getPropertyValue("background-color");
    await Promise.allSettled(document.getAnimations().map(animation => animation.finished));
  }, theme);
}

/** 可见绘制区域会被inert导航盖住，即使elementFromPoint跳过它，文档也没有横向溢出。 */
async function layoutFacts(page: Page) {
  return page.evaluate(() => {
    const nav = document.querySelector<HTMLElement>(".sidebar")!;
    const heading = document.querySelector("h1")!.getBoundingClientRect();
    const content = document.querySelector("main")!.getBoundingClientRect();
    const panel = document.querySelector('[aria-label="草稿高阶表达式"]')!.getBoundingClientRect();
    const rectangle = nav.getBoundingClientRect();
    const style = getComputedStyle(nav);
    return {
      sidebarRight: rectangle.right,
      closedNavigationPaintsOverTitle: style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity) > 0
        && rectangle.right > heading.left && rectangle.left < heading.right && rectangle.bottom > heading.top && rectangle.top < heading.bottom,
      titleLeft: heading.left, titleRight: heading.right, contentLeft: content.left, contentRight: content.right,
      panelLeft: panel.left, panelRight: panel.right, viewport: innerWidth,
      documentFits: document.documentElement.scrollWidth <= innerWidth + 1,
    };
  });
}

for (const theme of ["dark", "light"] as const) {
  test(`${theme}桌面缩到390后稳定内容完整、抽屉可开关、enabled按钮颜色可读`, async ({ page }) => {
    await layoutFixture(page, theme);
    await expect(page.getByRole("heading", { name: "本体资产与草稿" })).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    // 保留产品200ms动画；稳定截图/断言必须等待退出完成，不能只查scrollWidth或hit-test。
    await expect.poll(async () => (await layoutFacts(page)).sidebarRight).toBeLessThanOrEqual(0);
    const facts = await layoutFacts(page);
    expect(facts.closedNavigationPaintsOverTitle).toBe(false);
    expect(facts.documentFits).toBe(true);
    for (const left of [facts.titleLeft, facts.contentLeft, facts.panelLeft]) expect(left).toBeGreaterThanOrEqual(0);
    for (const right of [facts.titleRight, facts.contentRight, facts.panelRight]) expect(right).toBeLessThanOrEqual(facts.viewport);
    const active = page.getByRole("button", { name: "高阶表达式", exact: true });
    const refresh = page.getByRole("button", { name: "刷新高阶表达式", exact: true });
    await active.focus();
    await page.keyboard.press("Tab");
    await expect(refresh).toBeFocused();
    const contrast = await page.locator('.button').evaluateAll(buttons => {
      const luminance = (rgba: string) => {
        const channels = rgba.match(/[\d.]+/g)!.slice(0, 3).map(value => Number(value) / 255)
          .map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
        return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
      };
      return buttons.map(button => {
        const style = getComputedStyle(button), text = luminance(style.color), background = luminance(style.backgroundColor);
        return { label: button.textContent, foreground: style.color, background: style.backgroundColor,
          opacity: Number(style.opacity), enabled: !(button as HTMLButtonElement).disabled,
          ratio: (Math.max(text, background) + .05) / (Math.min(text, background) + .05) };
      });
    });
    for (const button of contrast) {
      expect(button.enabled).toBe(true);
      expect(button.opacity).toBe(1);
      expect(button.ratio).toBeGreaterThanOrEqual(4.5);
    }
    console.log(JSON.stringify({ theme, stableLayout: facts, enabledButtonContrast: contrast }));
    // 这里只控制夹具的抽屉状态；真实组件的ARIA/inert同步由产品浏览器独立验收。
    await page.locator('.sidebar').evaluate(element => { element.classList.add("is-open"); element.removeAttribute("inert"); });
    await expect(page.getByRole("button", { name: "本体资产", exact: true })).toBeInViewport();
    await page.locator('.sidebar').evaluate(element => { element.classList.remove("is-open"); element.setAttribute("inert", ""); });
    await expect.poll(async () => (await layoutFacts(page)).sidebarRight).toBeLessThanOrEqual(0);
  });
}

test("负例：文档无横向溢出仍可能被inert导航遮挡，必须检查真实绘制边界", async ({ page }) => {
  await layoutFixture(page, "dark");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(async () => (await layoutFacts(page)).sidebarRight).toBeLessThanOrEqual(0);
  // 仅夹具故障注入模拟原截图的动画中间帧，不修改或覆盖生产CSS。
  const fault = await page.addStyleTag({ content: ".sidebar{transform:translateX(-60%)!important;transition:none!important}" });
  const facts = await layoutFacts(page);
  expect(facts.documentFits).toBe(true);
  expect(facts.closedNavigationPaintsOverTitle).toBe(true);
  expect(facts.sidebarRight).toBeGreaterThan(0);
  await fault.evaluate(element => element.parentNode?.removeChild(element));
  await expect.poll(async () => (await layoutFacts(page)).sidebarRight).toBeLessThanOrEqual(0);
});
