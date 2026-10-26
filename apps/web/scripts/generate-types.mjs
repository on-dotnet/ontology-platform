import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { declarationsFor } from "./openapi-types.mjs";

/** 只从Master冻结或真实导出的OpenAPI生成类型，业务适配与生成内容分开维护。 */
for (const [sourceName, targetName] of [["g1-platform.openapi.json", "generated.ts"], ["g2-platform.openapi.json", "g2-generated.ts"]]) {
  const path = new URL(`../../../docs/contracts/${sourceName}`, import.meta.url);
  if (!existsSync(path)) continue;
  const source = JSON.parse(readFileSync(path, "utf8"));
  const target = new URL(`../src/lib/api/${targetName}`, import.meta.url);
  const generated = `// 从${sourceName}自动生成；运行pnpm generate:types，禁止手工编辑。\n\n${declarationsFor(source)}\n`;
  if (process.argv.includes("--check")) {
    if (!existsSync(target) || readFileSync(target, "utf8") !== generated) throw new Error(`${targetName}与规范OpenAPI生成结果不一致。`);
  } else {
    writeFileSync(target, generated);
  }
}
