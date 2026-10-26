import { test } from "vitest";
import assert from "node:assert/strict";
import { schemaType, declarationsFor } from "../../../scripts/openapi-types.mjs";

test("six-state enums and nullable unions stay precise", () => {
  assert.equal(schemaType({ type: "string", enum: ["FOUND", "EMPTY", "UNAVAILABLE"] }), '"FOUND" | "EMPTY" | "UNAVAILABLE"');
  assert.equal(schemaType({ anyOf: [{ $ref: "#/components/schemas/EvidenceRef" }, { type: "null" }] }), "EvidenceRef | null");
});

test("inline objects, dictionaries and required fields cannot become unknown", () => {
  assert.equal(schemaType({ type: "object", required: ["seq"], properties: { seq: { type: "integer" }, text: { type: "string" } }, additionalProperties: false }), '{ "seq": number; "text"?: string }');
  assert.equal(schemaType({ type: "object", additionalProperties: { type: "boolean" } }), "Record<string, boolean>");
});

test("event discriminators survive each typed payload and root union", () => {
  const source = { components: { schemas: { Delta: { type: "object", required: ["kind", "text"], properties: { kind: { const: "message.delta" }, text: { type: "string" } } }, EventPayload: { oneOf: [{ $ref: "#/components/schemas/Delta" }, { type: "null" }] } } } };
  const declarations = declarationsFor(source);
  assert.match(declarations, /"kind": "message.delta"/);
  assert.match(declarations, /export type EventPayload = Delta \| null/);
  assert.doesNotMatch(declarations, /unknown/);
});

// 真实运行OpenAPI快照中的全部组件均参与生成，不能忽略框架原生类型。
test("checked-in G2 artifact exactly matches canonical runtime schema and repeated generation", async () => {
  const { readFileSync } = await import("node:fs");
  const { execFileSync } = await import("node:child_process");
  const schema = JSON.parse(readFileSync(new URL("../../../../../docs/contracts/g2-platform.openapi.json", import.meta.url), "utf8"));
  const target = new URL("./g2-generated.ts", import.meta.url);
  const expected = `// 从g2-platform.openapi.json自动生成；运行pnpm generate:types，禁止手工编辑。\n\n${declarationsFor(schema)}\n`;
  const original = readFileSync(target, "utf8");
  assert.equal(original, expected);
  for (let iteration = 0; iteration < 2; iteration++) {
    execFileSync(process.execPath, [new URL("../../../scripts/generate-types.mjs", import.meta.url).pathname, "--check"]);
    assert.equal(readFileSync(target, "utf8"), original);
  }
});
