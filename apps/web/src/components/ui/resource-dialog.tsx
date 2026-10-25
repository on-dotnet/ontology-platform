"use client";
import { Dialog } from "@base-ui/react/dialog";
import type { PlatformResource } from "../../lib/api/generated";
/** Base UI 提供焦点锁定、Escape 关闭与还原焦点的资源详情。 */
export function ResourceDialog({ resource, traceId, auditId }: { resource: PlatformResource; traceId: string; auditId: string }) {
  return <Dialog.Root><Dialog.Trigger className="text-button">查看详情 <span aria-hidden="true">↗</span></Dialog.Trigger><Dialog.Portal><Dialog.Backdrop className="dialog-backdrop" /><Dialog.Popup className="dialog"><Dialog.Title>资源详情</Dialog.Title><Dialog.Description>服务端授权返回的开发合成资源与本次读取凭据。</Dialog.Description><dl className="detail-list"><dt>资源名称</dt><dd>{resource.name}</dd><dt>资源标识</dt><dd>{resource.id}</dd><dt>组织 / 厂区</dt><dd>{resource.organizationId} / {resource.siteId}</dd><dt>资源状态</dt><dd>{resource.status}</dd><dt>审计 ID</dt><dd className="mono">{auditId}</dd><dt>Trace ID</dt><dd className="mono">{traceId}</dd></dl><Dialog.Close className="button primary">关闭详情</Dialog.Close></Dialog.Popup></Dialog.Portal></Dialog.Root>;
}
