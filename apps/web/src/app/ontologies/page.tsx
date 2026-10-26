import { G2Page } from "../../features/ontology/server-page";
import { OntologyWorkspace } from "../../features/ontology/workspace";
export const dynamic = "force-dynamic";
/** 本体资产入口使用服务器验证的身份作用域。 */
export default function OntologiesPage() { return <G2Page section="ontologies">{identity => <OntologyWorkspace identity={identity} />}</G2Page>; }
