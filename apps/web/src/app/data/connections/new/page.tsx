import { ConnectionsPage } from "../../../../features/connections/server-page";
import { CreateConnection } from "../../../../features/connections/create";
/** 新建连接入口复用平台身份。 */
export default function Page() { return <ConnectionsPage>{identity => <CreateConnection identity={identity} />}</ConnectionsPage>; }
