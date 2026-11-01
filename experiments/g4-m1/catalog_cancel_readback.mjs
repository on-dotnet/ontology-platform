/** 只读验证已取消任务的准确深链接，不创建或取消新任务。 */
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const root=path.resolve(import.meta.dirname,'../..');
const privateDir=path.join(root,'.tools/security/g4-m1-recovery-001-20261101-01');
const runtime=JSON.parse(fs.readFileSync(path.join(privateDir,'runtime.json'),'utf8'));
const realm=JSON.parse(fs.readFileSync(runtime.realmFile,'utf8'));
const {chromium,expect}=createRequire(path.join(root,'apps/web/package.json'))('@playwright/test');
const report={taskId:'G4-M1-RECOVERY-001',startedUtc:new Date().toISOString(),status:'FAIL',phase:'launch',pageResponses:[],jobId:'75f491f14f33443ba6a1ee574819c996',connectionId:'1bf23f9d36bf4ceba09d745f04d8f743'};
let page;const browser=await chromium.launch({channel:'msedge',headless:true});
try {
 const context=await browser.newContext({serviceWorkers:'block',extraHTTPHeaders:{Connection:'close'}});
 await context.route('**/*',r=>['http://localhost:15100','http://localhost:15180'].includes(new URL(r.request().url()).origin)?r.continue():r.abort());
 page=await context.newPage();page.setDefaultTimeout(10000);
 report.phase='login_navigation';await page.goto('http://localhost:15100/auth/login?returnUrl=%2Fdata%2Fconnections');
 report.phase='login_credentials';const user=realm.identities['g2-operator-ab'];await page.locator('#username').fill(user.username);await page.locator('#password').fill(user.password);await page.locator('#kc-login').click();
 report.phase='login_return';await page.waitForURL(u=>u.origin==='http://localhost:15100'&&u.pathname==='/data/connections');
 report.phase='deep_link';report.pageErrors=[];page.on('pageerror',e=>report.pageErrors.push({name:e.name,category:'javascript_error'}));page.on('response',r=>{const u=new URL(r.url());if(!u.pathname.includes('/auth/')&&!u.pathname.includes('/realms/'))report.pageResponses.push({path:u.pathname.replace(/[a-f0-9]{32}/g,'{id}'),status:r.status()});});const response=page.waitForResponse(r=>r.url().endsWith('/discoveries/'+report.jobId)&&r.request().method()==='GET');
 const navigation=await page.goto('http://localhost:15100/data/connections/'+report.connectionId+'?job='+report.jobId);
 report.navigationStatus=navigation.status();report.jobUrlMatches=new URL(page.url()).searchParams.get('job')===report.jobId;if(report.navigationStatus!==200||!report.jobUrlMatches)throw new Error('navigation_assertion');report.phase='page_job_response';const actual=await response;const data=await actual.json();report.pageJobResponse={status:actual.status(),idMatch:data.jobId===report.jobId,connectionMatch:data.connectionId===report.connectionId,statusValue:data.status};if(actual.status()!==200||!report.pageJobResponse.idMatch||!report.pageJobResponse.connectionMatch||data.status!=='CANCELLED')throw new Error('identity_assertion');
 report.phase='visible_terminal';await expect(page.getByRole('status').filter({hasText:'目录发现：已取消'})).toBeVisible();report.cancelledVisible=true;
 await expect(page.getByRole('button',{name:'发现目录',exact:true})).toBeEnabled();
 await expect(page.getByRole('button',{name:'刷新详情',exact:true})).toBeEnabled();report.recoveryActionsEnabled=true;
 report.phase='reload';await page.reload();await expect(page.getByRole('status').filter({hasText:'目录发现：已取消'})).toBeVisible();await expect(page.getByRole('button',{name:'发现目录',exact:true})).toBeEnabled();await expect(page.getByRole('button',{name:'刷新详情',exact:true})).toBeEnabled();report.reloadRestored=true;report.status='PASS';
} catch(error){report.failure={category:error.name};process.exitCode=1;}
finally{await browser.close();report.completedUtc=new Date().toISOString();fs.writeFileSync(path.join(root,'artifacts/g4-m1-recovery-001/catalog-cancel-reload-asserted.json'),JSON.stringify(report,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({status:report.status,phase:report.phase}));}
