import { Suspense } from "react";
import { ConnectionsPage } from "../../../../features/connections/server-page";
import { ConnectionDetail } from "../../../../features/connections/detail";
/** 动态详情采用安装版本Next要求的异步params。 */
export default async function Page({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <ConnectionsPage>{identity => <Suspense fallback={<p role="status">正在读取详情…</p>}><ConnectionDetail key={id} id={id} canManage={identity.roles.includes("platform.operator")} /></Suspense>}</ConnectionsPage>; }
