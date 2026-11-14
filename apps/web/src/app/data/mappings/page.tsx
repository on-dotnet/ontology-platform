import { Suspense } from "react";
import { ConnectionsPage } from "../../../features/connections/server-page";
import { MappingList } from "../../../features/mappings/editor";
/** 同一可信SSR身份与Shell；深链恢复只读固定ID，不自动执行命令。 */
export default function Page() {
  return <ConnectionsPage>{identity => <Suspense fallback={<p role="status">正在读取映射工作区…</p>}><MappingList key={identity.subjectId}  /></Suspense>}</ConnectionsPage>;
}
