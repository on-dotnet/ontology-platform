import { G2Page } from "../../features/ontology/server-page";
import { ReleaseReview } from "../../features/publishing/review";
export const dynamic = "force-dynamic";
/** 发布入口共享可信身份边界，审核授权在服务端复核。 */
export default function ReleasesPage() { return <G2Page section="releases">{identity => <ReleaseReview identity={identity} />}</G2Page>; }
