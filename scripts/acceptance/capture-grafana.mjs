/** 仅使用本轮随机运维身份，登录后捕获中文真实数据面板；不保存浏览器存储或协议trace。 */
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const require = createRequire(path.join(root, 'apps/web/package.json'));
const { chromium } = require('@playwright/test');
const password = process.env.WAVE2_GRAFANA_PASSWORD;
if (!password) throw new Error('NOT_RUN: process-only Grafana test password required');
const output = path.join(root, 'docs/evidence/G1-WAVE2/master/grafana');
await fs.mkdir(output, { recursive: true });
let browser;
let stage = "launch";
try {
  browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, locale: 'zh-CN' });
  const page = await context.newPage();
  stage = 'login-page';
  await page.goto('http://localhost:15330/login');
  await page.locator('input[name="user"]').fill('platform-dev-admin');
  await page.locator('input[name="password"]').fill(password);
  stage = 'login-submit';
  await page.locator('button[type="submit"]').click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'));
  const records = [];
  for (const uid of ['platform-overview', 'platform-api', 'platform-dependencies', 'platform-errors']) {
    stage = 'dashboard-' + uid;
    await page.goto('http://localhost:15330/d/' + uid + '?from=now-15m&to=now&kiosk');
    await page.waitForLoadState('domcontentloaded');
    if (!new URL(page.url()).pathname.startsWith('/d/')) throw new Error('Dashboard navigation did not stay authenticated');
    await page.waitForTimeout(5000);
    // 页面已经离开认证表单；只截取本地配置即代码仪表盘，无密码或Cookie视图。
    await page.screenshot({ path: path.join(output, uid + '.png'), fullPage: true });
    records.push({ uid, status: 'CAPTURED_REAL_RUNTIME', screenshot: uid + '.png', source: 'local provisioned dashboard' });
  }
  await context.close();
  await fs.writeFile(path.join(output, 'capture.json'), JSON.stringify({ status: 'PASS', dashboards: records, authentication: 'process-only synthetic development identity; no storage export' }, null, 2) + '\n');
  console.log('PASS: four actual Chinese Grafana dashboard screenshots; no authentication material exported.');
} catch (error) {
  console.error('FAIL: Grafana safe screenshot capture stage=' + stage + ', category=' + error.name + '; details suppressed.');
  process.exitCode = 1;
} finally { await browser?.close(); }
