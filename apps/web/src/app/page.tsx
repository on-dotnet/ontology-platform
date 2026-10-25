import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { createPlatformClient, PlatformApiError } from "../lib/api/client";
import { getApiOrigin } from "../lib/api/server-config";
import { Workspace } from "../features/platform/workspace";
export const dynamic = "force-dynamic";
/** 身份只从可信 BFF 获取；Cookie 仅在服务端显式转发。 */
export default async function Home() {
  const cookieHeader = (await cookies()).toString();
  const client = createPlatformClient({ origin: getApiOrigin(), headers: { Cookie: cookieHeader } });
  let identity;
  try {
    identity = await client.me();
  } catch (error) {
    if (error instanceof PlatformApiError && error.status === 401) redirect("/auth/login?returnUrl=/");
    return <main id="main" className="standalone">
      <div className="brand-mark">O</div>
      <p className="eyebrow">连接状态</p>
      <h1>暂时无法连接平台</h1>
      <p>身份服务当前不可用。请稍后重试，已有权限不会在浏览器中被替代。</p>
      <Link className="button primary" href="/">重新连接</Link>
    </main>;
  }
  return <Workspace identity={identity} />;
}
