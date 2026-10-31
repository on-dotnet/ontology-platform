import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { declarationsFor } from "./openapi-types.mjs";

/** 只从Master冻结或真实导出的OpenAPI生成类型，业务适配与生成内容分开维护。 */
for (const [sourceName, targetName] of [["g1-platform.openapi.json", "generated.ts"], ["g2-platform.openapi.json", "g2-generated.ts"]]) {
  const path = new URL(`../../../docs/contracts/${sourceName}`, import.meta.url);
  if (!existsSync(path)) continue;
  const source = JSON.parse(readFileSync(path, "utf8"));
  const target = new URL(`../src/lib/api/${targetName}`, import.meta.url);
  // M5新增只读DTO先由同一Master规范Schema生成；实际路由导出后自动采用运行时Schema。
  const canonical = sourceName === "g2-platform.openapi.json"
    ? JSON.parse(readFileSync(new URL("../../../docs/contracts/g2-schemas.openapi.json", import.meta.url), "utf8")) : null;
  const pending = Object.fromEntries(Object.entries(canonical?.components?.schemas ?? {})
    .filter(([name]) => name.startsWith("OwlExpression") && !source.components?.schemas?.[name]));
  const supplementNote = Object.keys(pending).length ? "// 新只读DTO来自g2-models生成Schema；此补充不代表路由已实测。\n" : "";
  const merged = { ...source, components: { ...source.components, schemas: { ...pending, ...source.components?.schemas } } };
  const generated = `// 从${sourceName}自动生成；运行pnpm generate:types，禁止手工编辑。\n${supplementNote}\n${declarationsFor(merged)}\n`;
  if (process.argv.includes("--check")) {
    if (!existsSync(target) || readFileSync(target, "utf8") !== generated) throw new Error(`${targetName}与规范OpenAPI生成结果不一致。`);
  } else {
    writeFileSync(target, generated);
  }
}
