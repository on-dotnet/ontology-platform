import { G2Page } from "../../features/ontology/server-page";
import { QueryWorkspace } from "../../features/semantic/query-workspace";
export const dynamic = "force-dynamic";
/** 查询与Run复用服务端授权后的原平台Shell。 */
export default function AnalysisPage() { return <G2Page section="analysis">{() => <QueryWorkspace />}</G2Page>; }
