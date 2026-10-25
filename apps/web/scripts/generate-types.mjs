import { readFileSync, writeFileSync } from "node:fs";
const source = JSON.parse(readFileSync(new URL("../../../docs/contracts/g1-platform.openapi.json", import.meta.url), "utf8"));
function typeOf(schema) {
  if (schema.$ref) return schema.$ref.split("/").at(-1);
  if (Array.isArray(schema.type)) return schema.type.map(type => typeOf({ ...schema, type })).join(" | ");
  if (schema.type === "array") return `Array<${typeOf(schema.items)}>`;
  if (schema.type === "integer" || schema.type === "number") return "number";
  if (schema.type === "null") return "null";
  return schema.type === "string" || schema.type === "boolean" ? schema.type : "unknown";
}
const declarations = Object.entries(source.components.schemas).map(([name, schema]) => {
  const fields = Object.entries(schema.properties).map(([key, value]) => `  /** ${value.description || key} */\n  ${key}${schema.required?.includes(key) ? "" : "?"}: ${typeOf(value)};`).join("\n");
  return `export interface ${name} {\n${fields}\n}`;
});
writeFileSync(new URL("../src/lib/api/generated.ts", import.meta.url), `// 从冻结 OpenAPI 自动生成；请运行 pnpm generate:types，禁止手工编辑。\n\n${declarations.join("\n\n")}\n`);
