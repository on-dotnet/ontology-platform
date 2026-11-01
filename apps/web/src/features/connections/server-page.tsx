import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { createPlatformClient, PlatformApiError } from "../../lib/api/client";
import { getApiOrigin } from "../../lib/api/server-config";
import type { PlatformIdentity } from "../../lib/api/generated";
import { Workspace } from "../platform/workspace";
import "./connections.css";
/** 沿用既有可信SSR身份与Shell，客户端数据每次访问仍由API授权。 */
export async function ConnectionsPage({ children }: { children: (identity: PlatformIdentity) => React.ReactNode }) {
  let identity: PlatformIdentity;
  try { identity = await createPlatformClient({ origin: getApiOrigin(), headers: { Cookie: (await cookies()).toString() } }).me(); }
  catch (error) {
    if (error instanceof PlatformApiError && error.status === 401) redirect("/auth/login?returnUrl=/data/connections");
    return <main id="main" className="standalone"><h1>暂时无法读取平台身份</h1><p>请恢复连接后重试。</p><Link href="/data/connections">重新连接</Link></main>;
  }
  return <Workspace identity={identity} section="connections">{children(identity)}</Workspace>;
}
