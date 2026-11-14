import { Suspense } from "react";
import { ConnectionsPage } from "../../../../../../features/connections/server-page";
import { MappingAssessmentPage } from "../../../../../../features/mappings/assessment";
/** 同一可信SSR身份与Shell；深链恢复只读固定ID，不自动执行命令。 */
export default async function Page({ params }: { params: Promise<{ id: string; assessmentId: string }> }) {
  const { id, assessmentId } = await params;
  return <ConnectionsPage>{identity => <Suspense fallback={<p role="status">正在读取映射工作区…</p>}><MappingAssessmentPage key={identity.subjectId + id} mappingId={id} assessmentId={assessmentId} canEdit={identity.roles.includes("platform.operator")} /></Suspense>}</ConnectionsPage>;
}
