/** 验证真实发布页给出的Trace链接，在本地Grafana部署中实际返回该Trace；不截取认证页。 */
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve, relative, sep, isAbsolute } from 'node:path';
const root = resolve(import.meta.dirname, '../..');
const require = createRequire(resolve(root,'apps/web/package.json'));
const { chromium } = require('@playwright/test');
const runtimePath = resolve(process.argv[2] ?? '');
const runtimeRelative = relative(resolve(root, '.tools/security'), runtimePath);
if (!runtimeRelative || runtimeRelative === '..' || runtimeRelative.startsWith('..' + sep) || isAbsolute(runtimeRelative)) throw new Error('runtime_path_denied');
const runtime = JSON.parse(await readFile(runtimePath,'utf8'));
const realm = JSON.parse(await readFile(runtime.realmFile,'utf8'));
const browser = await chromium.launch({ channel:'msedge',headless:true });
const checks = [];
let phase = 'oidc';
let result;
try {
  const appContext = await browser.newContext({ viewport:{width:1440,height:1000} });
  const page = await appContext.newPage();
  await page.goto('http://localhost:15100/auth/login?returnUrl=%2Freleases');
  await page.locator('#username').fill(realm.identities['g2-operator-ab'].username);
  await page.locator('#password').fill(realm.identities['g2-operator-ab'].password);
  await page.locator('#kc-login').click();
  await page.waitForURL(url=>url.origin==='http://localhost:15100' && url.pathname==='/releases');
  const link = page.getByRole('link',{name:'在本地 Grafana 定位此 Trace',exact:true}).first();
  const href = await link.getAttribute('href');
  const target = new URL(href);
  const pane = JSON.parse(target.searchParams.get('panes')).trace;
  const traceId = pane.queries[0].query;
  if (target.origin!=='http://localhost:15330'||pane.datasource!=='platform-tempo'||!/^[a-f0-9]{32}$/.test(traceId)) throw new Error('unexpected_runtime_link');
  checks.push('actual_release_page_generated_valid_precise_trace_link');
  await appContext.close();
  phase = 'grafana_login';
  const context = await browser.newContext({ viewport:{width:1440,height:1100},locale:'zh-CN' });
  const grafana = await context.newPage();
  await grafana.goto('http://localhost:15330/login');
  await grafana.locator('input[name="user"]').fill('platform-dev-admin');
  await grafana.locator('input[name="password"]').fill(runtime.grafanaPassword);
  await grafana.locator('button[type="submit"]').click();
  await grafana.waitForURL(url=>!url.pathname.startsWith('/login'));
  phase = 'actual_tempo_deeplink';
  const observed = [];
  grafana.on('response',async response=>{
    if (response.url().includes('/api/ds/query')||response.url().includes('/api/datasources/proxy/uid/platform-tempo/')) {
      try { observed.push({status:response.status(),value:await response.json()}); } catch { }
    }
  });
  await grafana.goto(href);
  for (let count=0;count<30;count++) {
    if (observed.some(item=>item.status===200 && JSON.stringify(item.value).includes(traceId))) break;
    await grafana.waitForTimeout(1000);
  }
  const actual = observed.find(item=>item.status===200 && JSON.stringify(item.value).includes(traceId));
  if (!actual) throw new Error('trace_not_rendered_from_actual_link');
  checks.push('deployed_grafana_tempo_query_returns_requested_trace');
  const frames = Object.values(actual.value.results ?? {}).flatMap(value=>value.frames ?? []);
  if (!frames.some(frame=>frame.data?.values?.some(column=>column.length>0))) throw new Error('empty_trace_frames');
  checks.push('actual_trace_data_frame_is_nonempty');
  await grafana.waitForTimeout(700);
  if (new URL(grafana.url()).pathname!=='/explore') throw new Error('unexpected_navigation');
  await grafana.screenshot({path:resolve(root,'docs/evidence/G2-THIN-SLICE-001/master/screenshots/live-grafana-trace.png'),fullPage:true});
  checks.push('authenticated_actual_trace_view_captured');
  result={status:'PASS',checks,traceId,datasource:'platform-tempo',scope:'actual runtime link and deployed Grafana/Tempo, no storage/network authentication export'};
} catch (error) {
  result={status:'FAIL',checks,phase,category:error.name,details:'SUPPRESSED'};
  process.exitCode=1;
} finally {
  await browser.close();
  await writeFile(resolve(root,'docs/evidence/G2-THIN-SLICE-001/master/trace-browser.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify({status:result.status,checks:checks.length,phase:result.phase}));
}
