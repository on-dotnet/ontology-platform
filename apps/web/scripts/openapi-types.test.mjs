import { test } from "node:test";
import assert from "node:assert/strict";
import { schemaType, declarationsFor } from "./openapi-types.mjs";

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
