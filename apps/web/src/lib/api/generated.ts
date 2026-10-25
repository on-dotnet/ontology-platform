// 从冻结 OpenAPI 自动生成；请运行 pnpm generate:types，禁止手工编辑。

export interface PlatformScope {
  /** 组织范围标识。 */
  organizationId: string;
  /** 厂区范围标识。 */
  siteId: string;
}

export interface PlatformIdentity {
  /** 身份提供者验证通过的主体标识。 */
  subjectId: string;
  /** 界面显示名，不承载秘密声明。 */
  displayName: string;
  /** 服务器认可的平台角色集合。 */
  roles: Array<string>;
  /** 服务器认可的组织与厂区范围。 */
  scopes: Array<PlatformScope>;
}

export interface PlatformResource {
  /** 资源稳定标识。 */
  id: string;
  /** 资源中文显示名称。 */
  name: string;
  /** 资源所属组织。 */
  organizationId: string;
  /** 资源所属厂区。 */
  siteId: string;
  /** 明确说明资源为开发合成样例的状态。 */
  status: string;
}

export interface PlatformResourceList {
  /** 本次真正获准读取的资源。 */
  items: Array<PlatformResource>;
  /** 已经提交的PG访问审计标识。 */
  auditId: string;
  /** 当前请求的分布式跟踪标识。 */
  traceId: string;
}

export interface PlatformAuditEntry {
  /** 不可变审计事件标识。 */
  id: string;
  /** 审计发生的UTC时间。 */
  occurredAtUtc: string;
  /** 服务端解析的主体或anonymous标识。 */
  actor: string;
  /** 固定语义的审计操作代码。 */
  action: string;
  /** 被访问的平台资源标识或受控路径。 */
  resource: string;
  /** 允许、拒绝或失败的固定结果代码。 */
  outcome: string;
  /** 与运行日志和Trace关联的标识。 */
  traceId: string;
  /** 经过格式验证的请求关联标识。 */
  correlationId: string;
  /** 事件适用的组织范围，匿名时可空。 */
  organizationId: string | null;
  /** 事件适用的厂区范围，匿名时可空。 */
  siteId: string | null;
}

export interface CsrfResponse {
  /** 同源写请求需要回传的CSRF请求值。 */
  requestToken: string;
}

export interface PlatformProblem {
  /** type */
  type: string;
  /** title */
  title: string;
  /** status */
  status: number;
  /** detail */
  detail?: string;
  /** code */
  code: string;
  /** traceId */
  traceId: string;
  /** correlationId */
  correlationId: string;
}
