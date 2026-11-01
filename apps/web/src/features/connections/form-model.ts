import type { ConnectionConfig } from "../../lib/api/g4-generated";

/** 受控表单的展示模型；仅在提交时投影到唯一生成的传输合同。 */
export type ConnectionForm = { displayName: string; type: ConnectionType; values: Record<string, string> };
export const connectionTypes = ["POSTGRESQL", "ORACLE", "DORIS", "TDENGINE", "WEB_API"] as const;
export type ConnectionType = typeof connectionTypes[number];
export const typeLabels: Record<ConnectionType, string> = { POSTGRESQL: "PostgreSQL", ORACLE: "Oracle", DORIS: "Doris", TDENGINE: "TDengine", WEB_API: "Web API" };
/** 字段描述只控制展示，不构成第二套服务端DTO。 */
export type FormField = { key: string; label: string; initial: string; choices?: string[]; optional?: boolean };
export const formFields: Record<ConnectionType, FormField[]> = {
  POSTGRESQL: [{ key: "host", label: "主机", initial: "pg-source" }, { key: "port", label: "端口", initial: "5432" }, { key: "database", label: "数据库", initial: "fixture" }, { key: "username", label: "只读用户名", initial: "fixture_reader" }, { key: "sslMode", label: "TLS 验证", initial: "VerifyFull", choices: ["VerifyFull", "VerifyCA", "Require"] }, { key: "allowedSchemas", label: "允许的 Schema（逗号分隔）", initial: "production" }],
  ORACLE: [{ key: "host", label: "主机", initial: "" }, { key: "port", label: "端口", initial: "1521" }, { key: "serviceName", label: "服务名称（Service Name）", initial: "" }, { key: "username", label: "用户名", initial: "" }, { key: "tls", label: "TLS 加密", initial: "true", choices: ["true", "false"] }, { key: "allowedOwners", label: "允许的 Owner（逗号分隔）", initial: "" }],
  DORIS: [{ key: "feHost", label: "FE 主机", initial: "" }, { key: "queryPort", label: "查询端口", initial: "9030" }, { key: "catalog", label: "目录", initial: "" }, { key: "database", label: "数据库", initial: "" }, { key: "username", label: "用户名", initial: "" }, { key: "tls", label: "TLS 加密", initial: "true", choices: ["true", "false"] }],
  TDENGINE: [{ key: "wsUrl", label: "WebSocket 地址", initial: "" }, { key: "database", label: "数据库", initial: "" }, { key: "timePrecision", label: "时间精度", initial: "MILLISECOND", choices: ["MILLISECOND", "MICROSECOND", "NANOSECOND", "UNKNOWN"] }, { key: "timeZone", label: "时区（可选）", initial: "", optional: true }],
  WEB_API: [{ key: "baseOrigin", label: "已批准 HTTPS 源站", initial: "" }, { key: "operationId", label: "已批准操作", initial: "" }, { key: "method", label: "请求方法", initial: "GET", choices: ["GET"] }, { key: "approvedPath", label: "已批准路径", initial: "/" }, { key: "authentication", label: "认证方式", initial: "NONE", choices: ["NONE", "API_KEY_REF", "OAUTH_CLIENT_CREDENTIALS_REF"] }, { key: "pagination", label: "分页方式", initial: "NONE", choices: ["NONE", "PAGE", "OFFSET", "CURSOR", "LINK"] }, { key: "hostPolicyRef", label: "网络策略引用", initial: "" }],
};
/** 切换类型时仅保留名称，不携带其它类型字段或敏感引用。 */
export function newForm(type: ConnectionType = "POSTGRESQL", displayName = ""): ConnectionForm {
  return { displayName, type, values: Object.fromEntries(formFields[type].map(field => [field.key, field.initial])) };
}
/** 从服务器非秘密配置恢复编辑，不读取或虚构任何密码。 */
export function formFromConfig(displayName: string, config: ConnectionConfig): ConnectionForm {
  return { displayName, type: config.type, values: Object.fromEntries(Object.entries(config.profile).map(([key, value]) => [key, Array.isArray(value) ? value.join(", ") : value == null ? "" : String(value)])) };
}
/** 在请求前展示字段级错误；服务端仍执行全部授权和网络策略。 */
export function validateForm(form: ConnectionForm): Record<string, string> {
  const errors: Record<string, string> = {};
  const text = (value: string, max: number) => Boolean(value.trim()) && value.length <= max && !/[\u0000-\u001f\u007f-\u009f]/.test(value);
  if (!text(form.displayName, 128)) errors.displayName = "请输入 1–128 字的连接名称。";
  for (const field of formFields[form.type]) {
    const value = form.values[field.key] ?? "";
    const max = ["host", "feHost"].includes(field.key) ? 253 : ["username", "database"].includes(field.key) ? 63 : field.key === "approvedPath" ? 512 : 128;
    if (!(field.optional && value === "") && !text(value, ["wsUrl", "baseOrigin", "allowedSchemas", "allowedOwners"].includes(field.key) ? 2048 : max)) errors[field.key] = "请填写有效值，勿包含控制字符或超长文本。";
    if (field.choices && !field.choices.includes(value)) errors[field.key] = "请选择有效选项。";
    if (["port", "queryPort"].includes(field.key) && (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > 65535)) errors[field.key] = "端口须为 1–65535 的整数。";
    if (["host", "feHost"].includes(field.key) && !/^[A-Za-z0-9][A-Za-z0-9.-]*$/.test(value)) errors[field.key] = "请输入单一主机名，不能填 URL 或连接串。";
    if (["allowedSchemas", "allowedOwners"].includes(field.key)) {
      const names = value.split(",").map(name => name.trim());
      if (names.length > 16 || new Set(names).size !== names.length || names.some(name => !/^[A-Za-z_][A-Za-z0-9_]{0,62}$/.test(name))) errors[field.key] = "请填 1–16 个不重复的合法标识符，以逗号分隔。";
    }
    if (["wsUrl", "baseOrigin"].includes(field.key)) {
      try {
        const uri = new URL(value);
        if (uri.username || uri.password || (field.key === "wsUrl" ? !["ws:", "wss:"].includes(uri.protocol) : uri.protocol !== "https:" || uri.origin !== value)) errors[field.key] = "地址格式不正确，不能含凭据；源站不能含路径或查询。";
      } catch { errors[field.key] = "请输入完整有效地址。"; }
    }
    if (field.key === "approvedPath" && (!value.startsWith("/") || value.startsWith("//"))) errors[field.key] = "路径须以单个 / 开始。";
  }
  return errors;
}
/** 精确构造各类型profile；不发送表单展示字段或其它类型遗留字段。 */
export function configFromForm(form: ConnectionForm): ConnectionConfig {
  const v = form.values;
  const names = (value: string) => value.split(",").map(name => name.trim());
  switch (form.type) {
    case "POSTGRESQL": return { type: form.type, profile: { host: v.host, port: Number(v.port), database: v.database, username: v.username, sslMode: v.sslMode, allowedSchemas: names(v.allowedSchemas) } };
    case "ORACLE": return { type: form.type, profile: { host: v.host, port: Number(v.port), serviceName: v.serviceName, username: v.username, tls: v.tls === "true", allowedOwners: names(v.allowedOwners) } };
    case "DORIS": return { type: form.type, profile: { feHost: v.feHost, queryPort: Number(v.queryPort), catalog: v.catalog, database: v.database, username: v.username, tls: v.tls === "true" } };
    case "TDENGINE": return { type: form.type, profile: { wsUrl: v.wsUrl, database: v.database, timePrecision: v.timePrecision, timeZone: v.timeZone || null } };
    case "WEB_API": return { type: form.type, profile: { baseOrigin: v.baseOrigin, operationId: v.operationId, method: v.method, approvedPath: v.approvedPath, authentication: v.authentication, pagination: v.pagination, hostPolicyRef: v.hostPolicyRef } };
  }
}
