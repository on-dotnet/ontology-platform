/** 仅本任务新runtime的短真实浏览器链；不录制登录、网络、截图或凭据。 */
import {readFile, lstat, realpath} from 'node:fs/promises';
import {resolve, relative, sep} from 'node:path';
import {createRequire} from 'node:module';
const root=resolve(import.meta.dirname,'../..');
let browser;
let phase='runtime';
let probeStages=[];
const check=(value,code)=>{if(!value)throw new Error(code);};
async function privateFile(path){
 const absolute=resolve(path), prefix=resolve(root,'.tools/security/g4-eng-workflow-001')+sep;
 check(absolute.startsWith(prefix)&&await realpath(absolute)===absolute,'PRIVATE_BOUNDARY');
 check((await lstat(absolute)).isFile(),'PRIVATE_FILE');
 return readFile(absolute,'utf8');
}
try{
 const file=process.argv[2];const runtime=JSON.parse(await privateFile(file));
 check(runtime.taskId==='G4-ENG-WORKFLOW-001'&&/^wf-[0-9a-f]{12}$/.test(runtime.runId)&&runtime.worktree===root,'RUNTIME_IDENTITY');
 check(resolve(file)===resolve(root,'.tools/security/g4-eng-workflow-001',runtime.runId,'runtime.json'),'RUN_PATH');
 check(runtime.publicOrigin==='http://localhost:15100','ORIGIN');
 const realm=JSON.parse(await privateFile(runtime.realmFile));
 check(/^http:\/\/localhost:15180\/realms\/g2-[a-f0-9]+$/.test(realm.authority),'AUTHORITY');
 const secret=(await privateFile(runtime.sourceSecretFile)).trim();
 const require=createRequire(resolve(root,'apps/web/package.json'));
 const {chromium,expect}=require('@playwright/test');
 browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({serviceWorkers:'block'});
 await context.route('**/*',route=>new Set([runtime.publicOrigin,'http://localhost:15180']).has(new URL(route.request().url()).origin)?route.continue():route.abort());
 context.setDefaultTimeout(15000);
 const page=await context.newPage(),user=realm.identities['g2-operator-ab'];
 phase='oidc';
 await page.goto(runtime.publicOrigin+'/auth/login?returnUrl=%2Fdata%2Fconnections');
 await page.locator('#username').fill(user.username);await page.locator('#password').fill(user.password);await page.locator('#kc-login').click();
 await page.waitForURL(url=>url.origin===runtime.publicOrigin&&url.pathname==='/data/connections');
 const cookie=(await context.cookies()).find(x=>x.name==='.OntologyPlatform.Session');check(cookie?.httpOnly&&cookie.sameSite==='Lax','SESSION_COOKIE');
 await expect(page.locator('.connections-workspace > section.connection-card')).toBeVisible();
 phase='csrf_rejection';
 const denied=await context.request.post(runtime.publicOrigin+'/api/v1/connection-secrets',{data:'{',headers:{Origin:runtime.publicOrigin,'Content-Type':'application/json'},maxRedirects:0});
 check(denied.status()===403,'CSRF_NOT_REJECTED');
 phase='ui_pg_draft';
 await page.getByRole('link',{name:'新建连接',exact:true}).click();
 await page.getByRole('combobox',{name:/^数据源类型/}).selectOption('POSTGRESQL');
 await page.locator('input[name=displayName]').fill('Workflow '+runtime.runId);
 for(const [name,value]of Object.entries({host:'pg-source',port:'5432',database:'fixture',username:'fixture_reader',allowedSchemas:'production'}))await page.locator('input[name='+name+']').fill(value);
 await page.locator('select[name=sslMode]').selectOption('VerifyFull');
 await page.getByRole('combobox',{name:/^所属厂区/}).selectOption('org-demo/site-a');
 await page.getByLabel('重新输入密码',{exact:true}).fill(secret);
 async function click(label,path,status){
  const [response]=await Promise.all([page.waitForResponse(r=>new URL(r.url()).pathname===path&&r.request().method()==='POST'),page.getByRole('button',{name:label,exact:true}).click()]);
  check(response.status()===status,'UNEXPECTED_RESPONSE');return response.json();
 }
 await click('安全录入凭据','/api/v1/connection-secrets',201);
 const probe=await click('测试草稿','/api/v1/connections/tests',200);
 probeStages=(probe.stages??[]).filter(s=>['NETWORK','TLS','AUTH','READ_ONLY','METADATA'].includes(s.name)).map(s=>({name:s.name,status:['PASS','FAIL','NOT_RUN'].includes(s.status)?s.status:'UNKNOWN'}));
 check(probe.status==='TEST_OK'&&['NETWORK','TLS','AUTH','READ_ONLY','METADATA'].every(name=>probe.stages.some(s=>s.name===name&&s.status==='PASS')),'PG_PROBE');
 await expect(page.getByRole('region',{name:'连接测试报告'}).locator('ol li')).toHaveCount(5);
 check(!(await page.locator('body').innerText()).includes(secret),'VISIBLE_SECRET');
 console.log(JSON.stringify({status:'PASS',tests:2,skipped:0,taskId:runtime.taskId,runId:runtime.runId,checks:['OIDC_UI_PG_PROBE','AUTHENTICATED_CSRF_REJECTION']}));
}catch(error){
 console.log(JSON.stringify({status:'FAIL',tests:0,skipped:0,phase,probeStages,reason:error instanceof Error&&/^[A-Z_]+$/.test(error.message)?error.message:'BROWSER_OR_TRANSPORT'}));process.exitCode=1;
}finally{if(browser)await browser.close();}
