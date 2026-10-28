import assert from 'node:assert/strict';
import { readFile, mkdir } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
const root=process.argv[2];
assert.ok(root,'传入独立工作树绝对路径');
const { runM3Checks } = await import(pathToFileURL(root + '/scripts/acceptance/g3-m3-browser.mjs'));
assert.equal(typeof runM3Checks,'function');
process.env.PLATFORM_EVIDENCE_DIR='docs/evidence/G3-M3-001/WEB/gate-fixture';
await mkdir(root+'/'+process.env.PLATFORM_EVIDENCE_DIR,{recursive:true});
let rejected=false;
try {
 await runM3Checks({root,origin:'http://127.0.0.1:1',operator:{},viewer:{api:{get:async()=>({status:()=>503,json:async()=>({})})}},single:{},apiOnly:true,
  command:revision=>({expectedRevision:revision}),check:()=>{},setPhase:()=>{}});
} catch { rejected=true; }
assert.equal(rejected,true);
const report=JSON.parse(await readFile(root+'/'+process.env.PLATFORM_EVIDENCE_DIR+'/m3-api.json','utf8'));
assert.equal(report.status,'FAIL');
assert.equal(report.checks.filter(item=>item.status==='FAIL').length,1);
assert.equal(report.checks.at(-1).status,'FAIL');
assert.ok(report.notRun.includes('UI / publication / formal query / Run / SSE / rollback'));
process.exitCode=0;
console.log('PASS: controlled 503 cannot create M3 product PASS; partial checks persisted. NOT_PRODUCT_VALIDATION.');
