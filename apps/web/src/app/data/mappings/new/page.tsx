import { Suspense } from "react";
import { ConnectionsPage } from "../../../../features/connections/server-page";
import { MappingCreate } from "../../../../features/mappings/editor";
/** 同一可信SSR身份与Shell；深链恢复只读固定ID，不自动执行命令。 */
export default async function Page({ searchParams }: { searchParams: Promise<{ snapshotId?: string }> }) {
  const query = await searchParams;
  return <ConnectionsPage>{identity => <Suspense fallback={<p role="status">正在读取映射工作区…</p>}><MappingCreate key={identity.subjectId} canEdit={identity.roles.includes("platform.operator")} initialSnapshot={query.snapshotId} /></Suspense>}</ConnectionsPage>;
}
