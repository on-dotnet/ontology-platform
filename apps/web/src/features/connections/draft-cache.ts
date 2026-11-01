import type { PlatformIdentity } from "../../lib/api/generated";
import { connectionTypes, formFields, type ConnectionForm } from "./form-model";
/** 草稿仅按当前身份、角色和完整授权范围隔离；不缓存凭据、引用或服务端数据。 */
export function draftCacheKey(identity: PlatformIdentity) {
  return `connection-form:${JSON.stringify([identity.subjectId, [...identity.roles].sort(), identity.scopes.map(scope => [scope.organizationId, scope.siteId]).sort()])}`;
}
/** 白名单序列化仅包含当前类型的受控非秘密输入。 */
export function encodeDraft(form: ConnectionForm): string {
  return JSON.stringify({ displayName: form.displayName, type: form.type, values: Object.fromEntries(formFields[form.type].map(field => [field.key, ["wsUrl", "baseOrigin"].includes(field.key) && /:\/\/[^/]*@/.test(form.values[field.key] ?? "") ? "" : form.values[field.key] ?? ""])) });
}
/** sessionStorage是不可信输入；拒绝超预算、错误类型和额外字段。 */
export function decodeDraft(value: string | null): ConnectionForm | null {
  if (!value || value.length > 20000) return null;
  try {
    const parsed = JSON.parse(value);
    if (!parsed || typeof parsed.displayName !== "string" || !connectionTypes.includes(parsed.type) || !parsed.values || typeof parsed.values !== "object") return null;
    const type = parsed.type as ConnectionForm["type"];
    if (Object.keys(parsed).sort().join() !== "displayName,type,values" || Object.keys(parsed.values).sort().join() !== formFields[type].map(field => field.key).sort().join()) return null;
    if (Object.values(parsed.values).some(field => typeof field !== "string")) return null;
    return { displayName: parsed.displayName, type, values: parsed.values };
  } catch { return null; }
}
