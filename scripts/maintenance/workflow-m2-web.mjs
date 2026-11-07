/** 当前M2真实浏览器/认证API闭环；只输出断言名称，不记录秘密、正文、网络或截图。 */
import {readFile,lstat,realpath,writeFile} from 'node:fs/promises';
import {resolve,sep} from 'node:path';
import {createRequire} from 'node:module';
import {randomUUID} from 'node:crypto';
const root=resolve(import.meta.dirname,'../..');
let browser,phase='runtime';const checks=[];
const check=(value,code)=>{if(!value)throw new Error(code);};
async function privateFile(path){const absolute=resolve(path);check(absolute.startsWith(resolve(root,'.tools/security/g4-m2-web-01')+sep)&&await realpath(absolute)===absolute&&(await lstat(absolute)).isFile(),'PRIVATE_BOUNDARY');return readFile(absolute,'utf8');}
const command=(revision=0)=>({commandId:randomUUID(),idempotencyKey:randomUUID(),expectedRevision:revision,reason:'M2合成验收'});
try{
 const file=process.argv[2],runtime=JSON.parse(await privateFile(file));
 check(runtime.taskId==='G4-M2-WEB-01'&&/^m2-[a-f0-9]{12}$/.test(runtime.runId)&&runtime.worktree===root,'RUNTIME_IDENTITY');
 check(resolve(file)===resolve(root,'.tools/security/g4-m2-web-01',runtime.runId,'runtime.json'),'RUN_PATH');
 check(runtime.publicOrigin==='http://localhost:15100','ORIGIN');
 const realm=JSON.parse(await privateFile(runtime.realmFile)),key=(await privateFile(runtime.sourceSecretFile)).trim();
 check(/^http:\/\/localhost:15180\/realms\/g2-[a-f0-9]+$/.test(realm.authority),'AUTHORITY');
 const fixture=resolve(runtime.webFixture);check(fixture===resolve(file,'../web-source'),'FIXTURE_PATH');
 const mode=async value=>{await privateFile(fixture+'/control.json');await writeFile(fixture+'/control.json',JSON.stringify({mode:value}));};
 const stats=async()=>JSON.parse(await privateFile(fixture+'/stats.json'));
 const {chromium,expect}=createRequire(resolve(root,'apps/web/package.json'))('@playwright/test');
 browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({serviceWorkers:'block'});
 await context.route('**/*',route=>new Set([runtime.publicOrigin,'http://localhost:15180']).has(new URL(route.request().url()).origin)?route.continue():route.abort());
 context.setDefaultTimeout(12000);const page=await context.newPage(),user=realm.identities['g2-operator-ab'];
 phase='oidc';await page.goto(runtime.publicOrigin+'/auth/login?returnUrl=%2Fdata%2Fconnections');
 await page.locator('#username').fill(user.username);await page.locator('#password').fill(user.password);await page.locator('#kc-login').click();
 await page.waitForURL(url=>url.origin===runtime.publicOrigin&&url.pathname==='/data/connections');
 const cookie=(await context.cookies()).find(x=>x.name==='.OntologyPlatform.Session');check(cookie?.httpOnly&&cookie.sameSite==='Lax','SESSION_COOKIE');checks.push('REAL_OIDC');
 const origin=runtime.publicOrigin;
 async function get(path){const response=await context.request.get(origin+path,{maxRedirects:0});return {status:response.status(),data:await response.json(),etag:response.headers().etag};}
 async function send(path,body,revision,method='POST'){
  const csrf=await get('/auth/csrf');check(csrf.status===200,'CSRF_TOKEN');
  const headers={Origin:origin,'X-CSRF-TOKEN':csrf.data.requestToken,'Content-Type':'application/json'};if(revision!==undefined){const resource=path.match(/^\/api\/v1\/connections\/[^/]+/);check(resource,'ETAG_RESOURCE');const current=await get(resource[0]);check(current.status===200&&current.etag,'ETAG_READ');headers['If-Match']=current.etag;}
  const response=await context.request.fetch(origin+path,{method,data:body,headers,maxRedirects:0});return {status:response.status(),data:await response.json(),etag:response.headers().etag};
 }
 const scope={organizationId:'org-demo',siteIds:['site-a']};
 const config={type:'WEB_API',profile:{baseOrigin:'https://web-source:8443',operationId:'fixture-items',method:'GET',approvedPath:'/v1/items',authentication:'API_KEY_REF',pagination:'NONE',hostPolicyRef:'g4-m2-web-01'}};
 const pg={type:'POSTGRESQL',profile:{host:'pg-source',port:5432,database:'fixture',username:'fixture_reader',sslMode:'VerifyFull',allowedSchemas:['production']}};
 async function intake(purpose='WEB_API_KEY',selection=scope){const body={secretValue:key,scopeSelection:selection,purpose,command:command()};const result=await send('/api/v1/connection-secrets',body);check(result.status===201,'INTAKE');return {body,...result};}
 const expiries=new Map();
 async function create(){const secret=await intake();const response=await send('/api/v1/connections',{displayName:'M2 '+randomUUID(),scopeSelection:scope,config,secretRef:secret.data.secretRef,command:command()});check(response.status===201,'CREATE');expiries.set(response.data.id,Date.parse(secret.data.expiresAtUtc));return response.data;}
 const base=id=>'/api/v1/connections/'+id;
 async function mutate(row,action){return send(base(row.id)+'/'+action,{command:command(row.configRevision)},row.configRevision);}
 async function probeEnable(row){let result=await mutate(row,'test');check(result.status===200&&result.data.status==='TEST_OK','TEST');result=await mutate(row,'enable');check(result.status===200&&result.data.state==='ACTIVE','ENABLE');return result.data;}
 async function until(predicate,code){for(let i=0;i<80;i++){if(await predicate())return;await new Promise(r=>setTimeout(r,50));}throw new Error(code);}
 phase='csrf';const denied=await context.request.post(origin+'/api/v1/connection-secrets',{data:'{',headers:{Origin:origin,'Content-Type':'application/json'},maxRedirects:0});check(denied.status()===403,'CSRF_REJECT');checks.push('AUTHENTICATED_CSRF_REJECTION');
 phase='negative_binding';const initial=await intake(),replay=await send('/api/v1/connection-secrets',initial.body);check(replay.status===201&&replay.data.secretRef===initial.data.secretRef,'INTAKE_REPLAY');
 check((await send('/api/v1/connection-secrets',{...initial.body,purpose:'POSTGRESQL_READONLY'})).status===409,'INTAKE_PURPOSE_CONFLICT');checks.push('INTAKE_REPLAY_AND_PURPOSE_CONFLICT');
 const pgSecret=await intake('POSTGRESQL_READONLY');
 for(const [profile,secret] of [[config,pgSecret],[pg,initial]]){
  for(const path of ['/api/v1/connections/tests','/api/v1/connections']){
   const body={config:profile,scopeSelection:scope,secretRef:secret.data.secretRef,command:command()};if(path==='/api/v1/connections')body.displayName='拒绝跨用途';
   check((await send(path,body)).status===422,'CROSS_PURPOSE');
  }
 }
 checks.push('PG_WEB_BIDIRECTIONAL_CREATE_AND_DRAFT_REJECTION');
 const beforeUnsupported=(await stats()).requests;
 for(const profile of [{...config.profile,authentication:'NONE'},{...config.profile,authentication:'OAUTH_CLIENT_CREDENTIALS_REF'},...['PAGE','OFFSET','CURSOR','LINK'].map(pagination=>({...config.profile,pagination}))])check((await send('/api/v1/connections/tests',{config:{...config,profile},scopeSelection:scope,secretRef:initial.data.secretRef,command:command()})).status===422,'UNSUPPORTED');
 check((await stats()).requests===beforeUnsupported,'UNSUPPORTED_IO');checks.push('UNSUPPORTED_AUTH_PAGINATION_NO_IO');
 const bSecret=await intake('WEB_API_KEY',{organizationId:'org-demo',siteIds:['site-b']});
 check((await send('/api/v1/connections',{displayName:'跨范围',config,scopeSelection:scope,secretRef:bSecret.data.secretRef,command:command()})).status===422,'CROSS_SCOPE');checks.push('CROSS_SCOPE_BINDING_REJECT');
 phase='ui_web';await page.getByRole('link',{name:'新建连接',exact:true}).click();await page.getByRole('combobox',{name:/^数据源类型/}).selectOption('WEB_API');
 await page.locator('input[name=displayName]').fill('Web '+runtime.runId);
 for(const [name,value]of Object.entries(config.profile)){const select=page.locator('select[name='+name+']');if(await select.count())await select.selectOption(value);else await page.locator('input[name='+name+']').fill(value);}
 await page.getByRole('combobox',{name:/^所属厂区/}).selectOption('org-demo/site-a');await page.getByLabel('重新输入 API Key',{exact:true}).fill(key);
 async function click(label,path,status){const [response]=await Promise.all([page.waitForResponse(r=>new URL(r.url()).pathname===path&&r.request().method()==='POST'),page.getByRole('button',{name:label,exact:true}).click()]);check(response.status()===status,'UI_RESPONSE');return response.json();}
 await click('安全录入凭据','/api/v1/connection-secrets',201);
 const draft=await click('测试草稿','/api/v1/connections/tests',200);check(draft.status==='TEST_OK','UI_DRAFT');
 let row=await click('保存为草稿','/api/v1/connections',201);check(row.state==='DRAFT','UI_DRAFT_STATE');await page.waitForURL('**/data/connections/'+row.id);
 check((await click('重新测试',base(row.id)+'/test',200)).status==='TEST_OK','UI_SAVED_TEST');
 row=await click('明确启用连接',base(row.id)+'/enable',200);check(row.state==='ACTIVE','UI_ENABLE');
 const job=await click('发现目录',base(row.id)+'/discoveries',202);
 let done;await until(async()=>{done=(await get(base(row.id)+'/discoveries/'+job.jobId)).data;return done.status==='SUCCEEDED';},'UI_DISCOVERY');
 const catalog=await get('/api/v1/catalogs/'+done.snapshotId);check(catalog.status===200&&catalog.data.objects.length===1&&catalog.data.objects[0].fields.length===3,'CATALOG');
 check(!(await page.locator('body').innerText()).includes(key),'VISIBLE_KEY');checks.push('UI_CREATE_TEST_ENABLE_DISCOVER');
 phase='rotate_edit';check((await send(base(row.id)+'/rotate-secret',{secretRef:pgSecret.data.secretRef,command:command(row.configRevision)},row.configRevision)).status===422,'ROTATE_CROSS_PURPOSE');
 const rotated=await intake();const rotateBody={secretRef:rotated.data.secretRef,command:command(row.configRevision)};
 let changed=await send(base(row.id)+'/rotate-secret',rotateBody,row.configRevision);check(changed.status===200&&changed.data.state==='DRAFT'&&!changed.data.probeFresh,'ROTATE');row=changed.data;
 check((await send('/api/v1/connection-secrets',rotated.body)).status===422,'CONSUMED_REPLAY');
 check((await send('/api/v1/connections',{displayName:'重复消费',scopeSelection:scope,config,secretRef:rotated.data.secretRef,command:command()})).status===422,'DOUBLE_CONSUME');
 check((await mutate(row,'enable')).status===409,'OLD_PROBE');checks.push('ROTATE_INVALIDATES_PROBE_AND_SINGLE_USE');
 const beforeTarget=(await stats()).requests;
 for(const patch of [{config:{...config,profile:{...config.profile,operationId:'another'}}},{scopeSelection:{organizationId:'org-demo',siteIds:['site-b']}}])check((await send(base(row.id),{...patch,command:command(row.configRevision)},row.configRevision,'PATCH')).status>=400,'TARGET_SCOPE_EDIT');
 check((await stats()).requests===beforeTarget,'TARGET_EDIT_IO');checks.push('TARGET_SCOPE_EDIT_NO_IO');
 const edited=await send(base(row.id),{displayName:'已编辑 '+runtime.runId,command:command(row.configRevision)},row.configRevision,'PATCH');check(edited.status===200&&!edited.data.probeFresh,'EDIT_INVALIDATES_PROBE');row=edited.data;
 row=await probeEnable(row);await page.reload();await page.getByRole('button',{name:'禁用连接',exact:true}).click();row=await click('确认禁用',base(row.id)+'/disable',200);check(row.state==='DISABLED','UI_DISABLE');
 const beforeDisabled=(await stats()).requests;check((await mutate(row,'test')).status===409,'DISABLED_TEST');check((await get(base(row.id)+'/catalogs')).status===403,'DISABLED_CATALOG');check((await stats()).requests===beforeDisabled,'DISABLED_IO');checks.push('UI_DISABLE_AND_NO_SUBSEQUENT_IO');
 phase='concurrent_cancel';
 for(const action of ['test','enable','catalogs','discoveries']){
  await mode('normal');let current=await create();if(action!=='test')current=await probeEnable(current);
  const initialStats=await stats();await mode('stall-body');
  let operation,jobId;
  if(action==='catalogs')operation=get(base(current.id)+'/catalogs');
  else if(action==='discoveries'){const queued=await mutate(current,'discoveries');check(queued.status===202,'QUEUE');jobId=queued.data.jobId;}
  else operation=mutate(current,action);
  await until(async()=>(await stats()).requests>initialStats.requests,'SOURCE_STARTED');
  check((await mutate(current,'disable')).status===200,'CONCURRENT_DISABLE');
  await until(async()=>(await stats()).aborted>initialStats.aborted,'SOURCE_ABORTED');
  if(operation){const result=await operation;if(action==='test')check(result.status===200&&['CANCELLED','TEST_FAILED'].includes(result.data.status)&&result.data.stale===true,'STALE_TEST_SUCCESS');else check(result.status===(action==='catalogs'?403:409),'STALE_MUTATION_SUCCESS');}
  if(jobId)await until(async()=>['CANCELLED','FAILED'].includes((await get(base(current.id)+'/discoveries/'+jobId)).data.status),'JOB_TERMINAL');
  const stopped=(await stats()).requests;await new Promise(r=>setTimeout(r,350));check((await stats()).requests===stopped,'POST_DISABLE_IO');checks.push('DISABLE_CANCELS_'+action.toUpperCase());
 }
 await mode('normal');let cancelRow=await probeEnable(await create());const cancelBefore=await stats();await mode('stall-body');const queued=await mutate(cancelRow,'discoveries');check(queued.status===202,'CANCEL_QUEUE');await until(async()=>(await stats()).requests>cancelBefore.requests,'CANCEL_SOURCE_STARTED');
 check((await send(base(cancelRow.id)+'/discoveries/'+queued.data.jobId+'/cancel',{command:command(cancelRow.configRevision)},cancelRow.configRevision)).status===200,'CANCEL_COMMAND');await until(async()=>(await stats()).aborted>cancelBefore.aborted,'CANCEL_SOURCE_ABORTED');await mode('normal');checks.push('EXPLICIT_CANCEL_CLOSES_SOCKET');
 phase='authorization';
 const scopeB={organizationId:'org-demo',siteIds:['site-b']},pgB=await intake('POSTGRESQL_READONLY',scopeB);const scopedPg=await send('/api/v1/connections',{displayName:'范围对照PG草稿',scopeSelection:scopeB,config:pg,secretRef:pgB.data.secretRef,command:command()});check(scopedPg.status===201,'SCOPE_CONTROL_CREATE');
 for(const [identity,kind] of [['g2-viewer-a','viewer'],['g2-operator-a','scope'],['g2-operator-a','owner']]){
  phase='authorization_'+kind+'_login';
  const child=await browser.newContext({serviceWorkers:'block'});await child.route('**/*',route=>new Set([origin,'http://localhost:15180']).has(new URL(route.request().url()).origin)?route.continue():route.abort());
  const tab=await child.newPage(),actor=realm.identities[identity];await tab.goto(origin+'/auth/login?returnUrl=%2F');await tab.locator('#username').fill(actor.username);await tab.locator('#password').fill(actor.password);await tab.locator('#kc-login').click();await tab.waitForURL(url=>url.origin===origin&&url.pathname==='/');phase='authorization_'+kind+'_api';
  const token=await (await child.request.get(origin+'/auth/csrf')).json();
  if(kind==='scope'){check((await child.request.get(origin+base(cancelRow.id))).status()===200,'READ_SCOPE_POSITIVE');check((await child.request.get(origin+base(scopedPg.data.id))).status()===403,'READ_SCOPE');}
  else {const body=kind==='viewer'?{secretValue:key,scopeSelection:scope,purpose:'WEB_API_KEY',command:command()}:{displayName:'不同owner',config,scopeSelection:scope,secretRef:initial.data.secretRef,command:command()};const response=await child.request.post(origin+(kind==='viewer'?'/api/v1/connection-secrets':'/api/v1/connections'),{data:body,headers:{Origin:origin,'X-CSRF-TOKEN':token.requestToken}});check(response.status()===(kind==='viewer'?403:422),'IDENTITY_REJECTION');}
  await child.close();checks.push('AUTHORIZATION_'+kind.toUpperCase());
 }
 phase='natural_expiry';
 const expires=Math.max(Date.parse(initial.data.expiresAtUtc),expiries.get(cancelRow.id));check(Number.isFinite(expires)&&expires<Date.now()+610000,'EXPIRY_BOUND');
 while(Date.now()<=expires+100){await writeFile(resolve(file,'../progress.json'),JSON.stringify({phase,secondsRemaining:Math.max(0,Math.ceil((expires-Date.now())/1000)),checks:checks.length}));await new Promise(resolve=>setTimeout(resolve,Math.min(5000,Math.max(100,expires-Date.now()+101))));}
 const expiryBefore=(await stats()).requests;
 for(const path of ['/api/v1/connections/tests','/api/v1/connections']){const body={config,scopeSelection:scope,secretRef:initial.data.secretRef,command:command()};if(path==='/api/v1/connections')body.displayName='自然过期';const result=await send(path,body);check(result.status===422&&result.data.code==='connection_secret_expired','EXPIRED_BINDING');}
 check((await send('/api/v1/connection-secrets',initial.body)).status===422,'EXPIRED_REPLAY');check((await stats()).requests===expiryBefore,'EXPIRED_IO');
 check((await mutate(cancelRow,'test')).data.status==='TEST_OK','BOUND_SECRET_TTL');checks.push('NATURAL_EXPIRY_NO_REACTIVATION_BOUND_SECRET_REMAINS_VALID');
 console.log(JSON.stringify({status:'PASS',tests:checks.length,skipped:0,taskId:runtime.taskId,runId:runtime.runId,checks}));
}catch(error){console.log(JSON.stringify({status:'FAIL',tests:checks.length,skipped:0,phase,checks,errorType:error?.name??'Unknown',reason:error instanceof Error&&/^[A-Z_]+$/.test(error.message)?error.message:'BROWSER_OR_TRANSPORT'}));process.exitCode=1;}
finally{if(browser)await browser.close();}
