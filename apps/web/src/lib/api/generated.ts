// 从g1-platform.openapi.json自动生成；运行pnpm generate:types，禁止手工编辑。

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export type PlatformScope = { "organizationId": string; "siteId": string };

export type PlatformIdentity = { "subjectId": string; "displayName": string; "roles": Array<string>; "scopes": Array<PlatformScope> };

export type PlatformResource = { "id": string; "name": string; "organizationId": string; "siteId": string; "status": string };

export type PlatformResourceList = { "items": Array<PlatformResource>; "auditId": string; "traceId": string };

export type PlatformAuditEntry = { "id": string; "occurredAtUtc": string; "actor": string; "action": string; "resource": string; "outcome": string; "traceId": string; "correlationId": string; "organizationId": string | null; "siteId": string | null; "scopeSiteIds": Array<string> | null };

export type CsrfResponse = { "requestToken": string };

export type PlatformProblem = { "type": string; "title": string; "status": number; "detail"?: string; "code": string; "traceId": string; "correlationId": string } & Record<string, JsonValue>;
