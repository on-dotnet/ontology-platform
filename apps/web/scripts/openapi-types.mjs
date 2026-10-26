/** 将标准OpenAPI 3.1/JSON Schema显式映射为TypeScript，保留枚举和联合信息。 */
export function schemaType(schema) {
  if (schema === true || schema == null) return "JsonValue";
  if (schema === false) return "never";
  if (Object.hasOwn(schema, "const")) return JSON.stringify(schema.const);
  if (schema.enum) return schema.enum.map(value => JSON.stringify(value)).join(" | ") || "never";
  if (schema.$ref) {
    if (!schema.$ref.startsWith("#/components/schemas/")) throw new Error("External schema references are not supported");
    const name = schema.$ref.split("/").at(-1);
    if (!/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(name)) throw new Error("Invalid schema identifier");
    return name;
  }
  if (schema.oneOf || schema.anyOf) return (schema.oneOf ?? schema.anyOf).map(schemaType).join(" | ");
  if (schema.allOf) return schema.allOf.map(value => `(${schemaType(value)})`).join(" & ");
  if (Array.isArray(schema.type)) return schema.type.map(type => schemaType({ ...schema, type })).join(" | ");
  if (schema.type === "array") return `Array<${schemaType(schema.items)}>`;
  if (schema.type === "integer" || schema.type === "number") return "number";
  if (schema.type === "null") return "null";
  if (schema.type === "string" || schema.type === "boolean") return schema.type;
  if (schema.type === "object" || schema.properties || Object.hasOwn(schema, "additionalProperties")) {
    const fields = Object.entries(schema.properties ?? {}).map(([key, value]) => `${JSON.stringify(key)}${schema.required?.includes(key) ? "" : "?"}: ${schemaType(value)}`);
    const body = fields.length ? `{ ${fields.join("; ")} }` : null;
    const dictionary = schema.additionalProperties !== false ? `Record<string, ${schemaType(schema.additionalProperties ?? true)}>` : null;
    if (body && dictionary) return `${body} & ${dictionary}`;
    return body ?? dictionary ?? "Record<string, never>";
  }
  return "JsonValue";
}

/** 所有模型用type声明统一处理对象、枚举、空值和判别联合，禁止静默扩大为unknown。 */
export function declarationsFor(source) {
  const aliases = Object.entries(source.components?.schemas ?? {}).map(([name, schema]) => {
    if (!/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(name)) throw new Error("Invalid schema identifier");
    return `export type ${name} = ${schemaType(schema)};`;
  });
  return "export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };\n\n" + aliases.join("\n\n");
}
