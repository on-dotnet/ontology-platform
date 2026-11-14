import { Suspense } from "react";
import { ConnectionsPage } from "../../../../features/connections/server-page";
import { MappingProposalPage } from "../../../../features/mappings/proposal";
/** 同一可信SSR身份与Shell；深链恢复只读固定ID，不自动执行命令。 */
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ConnectionsPage>{identity => <Suspense fallback={<p role="status">正在读取映射工作区…</p>}><MappingProposalPage key={identity.subjectId + id} id={id} subjectId={identity.subjectId} canReview={identity.roles.includes("platform.auditor")} canActivate={identity.roles.includes("platform.operator")} /></Suspense>}</ConnectionsPage>;
}
