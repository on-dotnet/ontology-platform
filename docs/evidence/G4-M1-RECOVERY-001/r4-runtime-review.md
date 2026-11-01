# R4 全栈分组运行独立准入

非作者 /root/recovery_reviewer 已核对6服务总5.25GiB（正常5服务4.5GiB）、任务4卷1552MiB、source/front均internal、4精确镜像均R3 A1、API/Web共享网络namespace、Keycloak/platform只front、最小私有挂载。源PG先12真实PASS且错误SAN1PASS。

Keycloak原镜像首build不能直接start --optimized，也不能在只读root下隐式build。增量获审compose SHA c575e270840ddc36f682ae4913a5c7b920704028136cdf352563f0fa045a258c、rendered SHA9af22abd2e68009d73d430a8ea5871d3e02018d5a6781529e6b9185e4e586f2b：只复制固定bin/conf/lib/providers/themes/LICENSE.txt/README.md/version.txt到已有512MiB卷runtime，不复制data；bash -ec确保kc.sh build --db=dev-file成功才写marker，随后optimized fixed issuer启动。实测build5430ms，start4.141s；卷188188KiB/524288KiB，无OOM，原root只读。

随后平台PG、API等待配置及Web按已审配置启动。发现Docker internal网络下HostConfig端口配置未形成实际NetworkSettings端口，宿主两种回环TCP拒绝，而容器内部身份HTTP200。Next启动后TS配置解析尝试SWC失败，普通Next页面短探针未完成，已精确停该任务Web保留失败。未安装SWC、未扩大网络。

定向修复新入口另待最终独立审查：固定宿主127.0.0.1两端口→精确web容器stdin/stdout真实TCP，跨入口8并发30秒期限；Next采用原生产manifest配置序列化机制。所有失败保留，不以Ready或静态配置冒充产品PASS。
