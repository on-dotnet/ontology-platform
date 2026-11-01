/** 真实浏览器仅延迟准确连接的响应交付，验证父子短HTTP操作双向互锁。 */
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
const root=path.resolve(import.meta.dirname,'../..'),privateDir=path.join(root,'.tools/security/g4-m1-recovery-001-20261101-01');
const runtime=JSON.parse(fs.readFileSync(path.join(privateDir,'runtime.json'),'utf8')),realm=JSON.parse(fs.readFileSync(runtime.realmFile,'utf8'));
const {chromium,expect}=createRequire(path.join(root,'apps/web/package.json'))('@playwright/test');
const id='a6b043f62e3241ab8e2f8f6b9911a00c',connectionPath='/api/v1/connections/'+id;
const report={taskId:'G4-M1-RECOVERY-001',connectionId:id,status:'FAIL',startedUtc:new Date().toISOString(),http:[],phase:'login'};
const ready=p=>Promise.race([p,new Promise((_,reject)=>setTimeout(()=>reject(new Error('handshake_timeout')),5000))]);
const browser=await chromium.launch({channel:'msedge',headless:true});let releaseGet,releaseDiscover;
try {
 const context=await browser.newContext({serviceWorkers:'block',extraHTTPHeaders:{Connection:'close'}});context.setDefaultTimeout(15000);
 await context.route('**/*',r=>['http://localhost:15100','http://localhost:15180'].includes(new URL(r.request().url()).origin)?r.continue():r.abort());
 const page=await context.newPage();await page.goto('http://localhost:15100/auth/login?returnUrl=%2Fdata%2Fconnections');const user=realm.identities['g2-operator-ab'];await page.locator('#username').fill(user.username);await page.locator('#password').fill(user.password);await page.locator('#kc-login').click();await page.waitForURL(u=>u.origin==='http://localhost:15100'&&u.pathname==='/data/connections');
 page.on('request',r=>{const u=new URL(r.url());if(u.pathname.startsWith(connectionPath))report.http.push({method:r.method(),route:u.pathname.replace(/[a-f0-9]{32}/g,'{id}')});});
 await page.goto('http://localhost:15100/data/connections/'+id);await expect(page.getByRole('button',{name:'重新测试',exact:true})).toBeEnabled();
 await page.locator('input[name=displayName]').fill('G4 synthetic concurrency witness');await page.getByRole('button',{name:'保存配置',exact:true}).click();await expect(page.getByRole('button',{name:'重新测试',exact:true})).toBeEnabled();
 await page.getByRole('button',{name:'重新测试',exact:true}).click();await expect(page.getByRole('button',{name:'明确启用连接',exact:true})).toBeEnabled();
 let holdParent=false,parentHeld,discoverHeld;const parentReady=new Promise(r=>parentHeld=r),discoverReady=new Promise(r=>discoverHeld=r);
 const getGate=new Promise(r=>releaseGet=r),discoverGate=new Promise(r=>releaseDiscover=r);
 await page.route('**/api/v1/connections/'+id,async route=>{
  if(route.request().method()==='GET'&&holdParent){holdParent=false;parentHeld();await Promise.race([getGate,new Promise(r=>setTimeout(r,4000))]);}
  await route.continue();
 });
 await page.route('**/api/v1/connections/'+id+'/enable',async route=>{try{const response=await route.fetch({timeout:5000,maxRedirects:0});if(response.status()!==200)throw new Error('enable_status');holdParent=true;await route.fulfill({response});}catch{report.routeFailure='enable_route';await route.abort().catch(()=>{});}});
 report.phase='parent_refresh_pending';await page.getByRole('button',{name:'明确启用连接',exact:true}).click();await ready(parentReady);
 await expect(page.getByRole('button',{name:'发现目录',exact:true})).toBeDisabled();
 const beforeDiscover=report.http.filter(x=>x.method==='POST'&&x.route.endsWith('/discoveries')).length;
 await page.getByRole('button',{name:'发现目录',exact:true}).evaluate(e=>e.click());
 if(report.http.filter(x=>x.method==='POST'&&x.route.endsWith('/discoveries')).length!==beforeDiscover)throw new Error('discovery_during_parent_refresh');report.parentPendingBlocksDiscovery=true;report.parentDelayMechanism='Hold exact connection GET before route.continue; no synthetic response';
 releaseGet();await expect(page.getByRole('button',{name:'发现目录',exact:true})).toBeEnabled();
 let discovered;
 await page.route('**/api/v1/connections/'+id+'/discoveries',async route=>{
  try{const response=await route.fetch({timeout:5000,maxRedirects:0});if(response.status()!==202)throw new Error('discover_status');discovered=await response.json();if(!/^[a-f0-9]{32}$/.test(discovered.jobId)||discovered.connectionId!==id||!['QUEUED','RUNNING'].includes(discovered.status))throw new Error('discovery_identity');discoverHeld();await Promise.race([discoverGate,new Promise(r=>setTimeout(r,4000))]);await route.fulfill({response});}catch{report.routeFailure='discover_route';await route.abort().catch(()=>{});}
 });
 report.phase='child_response_pending';await page.getByRole('button',{name:'发现目录',exact:true}).click();await ready(discoverReady);
 await expect(page.getByRole('button',{name:'刷新详情',exact:true})).toBeDisabled();await expect(page.getByRole('button',{name:'重新测试',exact:true})).toBeDisabled();
 const beforeRefresh=report.http.filter(x=>x.method==='GET'&&x.route==='/api/v1/connections/{id}').length;
 await page.getByRole('button',{name:'刷新详情',exact:true}).evaluate(e=>e.click());if(report.http.filter(x=>x.method==='GET'&&x.route==='/api/v1/connections/{id}').length!==beforeRefresh)throw new Error('refresh_during_discovery');report.childPendingBlocksParent=true;
 releaseDiscover();await page.waitForURL(u=>u.origin==='http://localhost:15100'&&u.pathname==='/data/connections/'+id&&u.searchParams.get('job')===discovered.jobId);report.jobId=discovered.jobId;report.jobUrlPreserved=true;
 report.phase='reload';await page.reload();await expect(page.getByRole('status').filter({hasText:'目录发现：已完成'})).toBeVisible();await expect(page.getByRole('button',{name:'刷新详情',exact:true})).toBeEnabled();await expect(page.getByRole('button',{name:'发现目录',exact:true})).toBeEnabled();report.reloadRestored=true;if(report.routeFailure)throw new Error('route_failure');report.status='PASS';
}catch(error){report.failure={category:error.name};process.exitCode=1;}
finally{releaseGet?.();releaseDiscover?.();await browser.close();report.completedUtc=new Date().toISOString();report.driverSha256=createHash('sha256').update(fs.readFileSync(import.meta.filename)).digest('hex');fs.writeFileSync(path.join(root,'artifacts/g4-m1-recovery-001/ui-interlock-real.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({status:report.status,phase:report.phase}));}
