/** 真实导出与冻结合同、生成类型逐字节/结构比较；隔离再生与篡改负例。 */
import { readFileSync, writeFileSync, mkdirSync, lstatSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { declarationsFor } from '../../apps/web/scripts/openapi-types.mjs';
const root = resolve(import.meta.dirname, '../..');
const sha = value => createHash('sha256').update(value).digest('hex');
const canonical = value => JSON.stringify(value, function(key, child) {
  return child && !Array.isArray(child) && typeof child === 'object'
    ? Object.fromEntries(Object.keys(child).sort().map(k => [k, child[k]])) : child;
});
export function compareDocument(actual, expected) {
  // Only transport-generated server origins can differ; paths/DTO/required/enums/errors stay exact.
  const project = value => { const copy = structuredClone(value); delete copy.servers; return copy; };
  if (canonical(project(actual)) !== canonical(project(expected))) throw new Error('OPENAPI_DRIFT');
}
export function compareTypes(actual, expected) {
  if (actual !== expected) throw new Error('GENERATED_CLIENT_DRIFT');
}
export function schemaMutations(frozen) {
  const schemas = frozen.components.schemas;
  const requiredKey = Object.keys(schemas).find(k => schemas[k].required?.length);
  const discriminator = schemas.ConnectionConfigPgConnectionConfig?.properties?.type;
  if (!requiredKey || canonical(discriminator?.enum) !== canonical(['POSTGRESQL'])) throw new Error('NEGATIVE_SCHEMA_MISSING');
  const requiredMutation=structuredClone(frozen); requiredMutation.components.schemas[requiredKey].required=[];
  const enumMutation=structuredClone(frozen); enumMutation.components.schemas.ConnectionConfigPgConnectionConfig.properties.type.enum.push('INVALID_TEST_ENUM');
  const dtoMutation=structuredClone(frozen); dtoMutation.components.schemas[requiredKey].properties.testAddedField={type:'string'};
  return [requiredMutation,enumMutation,dtoMutation];
}
function reject(work) { let caught = false; try { work(); } catch { caught = true; } if (!caught) throw new Error('NEGATIVE_ACCEPTED'); }
if (process.argv[1] === import.meta.filename) {
  const args = process.argv.slice(2);
  if (args.length !== 4 || args[0] !== '--runtime-openapi' || args[2] !== '--output') throw new Error('ARGUMENTS');
  const runtimeFile = resolve(args[1]), output = resolve(args[3]);
  for (const p of [runtimeFile, output]) {
    if (!p.startsWith(root + '/artifacts/g4-m1-main-integration-001/')) throw new Error('PATH_BOUNDARY');
    for (let x = p; x !== root; x = dirname(x)) {
      try { if (lstatSync(x).isSymbolicLink()) throw new Error('SYMLINK'); } catch (e) { if (e.code !== 'ENOENT') throw e; }
    }
  }
  mkdirSync(output, {recursive: false});
  const actual = JSON.parse(readFileSync(runtimeFile, 'utf8'));
  const frozen = JSON.parse(readFileSync(resolve(root, 'docs/contracts/g4-connections.openapi.json'), 'utf8'));
  compareDocument(actual, frozen);
  execFileSync(process.execPath, [resolve(root, 'apps/web/scripts/generate-types.mjs'), '--check'], {cwd: root});
  const pairs = [['g1-platform.openapi.json','generated.ts'],['g2-platform.openapi.json','g2-generated.ts'],['g4-connections.openapi.json','g4-generated.ts']];
  const generated = [];
  for (const [source, target] of pairs) {
    const doc = JSON.parse(readFileSync(resolve(root,'docs/contracts',source),'utf8'));
    const text = `// 从${source}自动生成；运行pnpm generate:types，禁止手工编辑。\n\n${declarationsFor(doc)}\n`;
    compareTypes(text,readFileSync(resolve(root,'apps/web/src/lib/api',target),'utf8'));
    writeFileSync(resolve(output,target),text,{flag:'wx'}); generated.push({source,target,sha256:sha(text)});
    reject(()=>compareTypes(text+'\n// changed client',text));
  }
  for(const mutation of schemaMutations(frozen)) reject(()=>compareDocument(mutation,frozen));
  console.log(JSON.stringify({status:'PASS',scope:'Actual exported G4 OpenAPI + frozen G1/G2/G4 generators; G3 contract schema is in G2',generated,negativeCases:6,runtimeSha256:sha(readFileSync(runtimeFile))}));
}
