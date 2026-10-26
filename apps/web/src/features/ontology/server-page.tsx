import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { createPlatformClient, PlatformApiError } from "../../lib/api/client";
import { getApiOrigin } from "../../lib/api/server-config";
import { Workspace } from "../platform/workspace";
import type { PlatformIdentity } from "../../lib/api/generated";
/** 沿用G1可信SSR身份和Shell；认证失败只转入原登录流程。 */
export async function G2Page({ section, children }: { section: "ontologies" | "releases" | "analysis"; children: (identity: PlatformIdentity) => React.ReactNode }) {
  let identity: PlatformIdentity;
  try { identity = await createPlatformClient({ origin: getApiOrigin(), headers: { Cookie: (await cookies()).toString() } }).me(); }
  catch (error) {
    if (error instanceof PlatformApiError && error.status === 401) redirect(`/auth/login?returnUrl=/${section}`);
    return <main id="main" className="standalone"><h1>暂时无法读取平台身份</h1><p>身份服务不可用，请重新连接。</p><Link href={`/${section}`} className="button">重新连接</Link></main>;
  }
  return <Workspace identity={identity} section={section}>{children(identity)}</Workspace>;
}
