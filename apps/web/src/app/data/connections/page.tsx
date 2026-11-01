import { Suspense } from "react";
import { ConnectionsPage } from "../../../features/connections/server-page";
import { ConnectionList } from "../../../features/connections/list";
/** 数据源列表入口，筛选参数由客户端受控读取。 */
export default function Page() { return <ConnectionsPage>{identity => <Suspense fallback={<p role="status">正在读取连接…</p>}><ConnectionList canManage={identity.roles.includes("platform.operator")} /></Suspense>}</ConnectionsPage>; }
