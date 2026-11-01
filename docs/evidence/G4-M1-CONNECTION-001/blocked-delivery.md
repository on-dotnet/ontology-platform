# G4-M1-CONNECTION-001 — BLOCKED / DRAFT / PARTIAL

用户已正式批准 P0–P5 全范围；授权没有撤销。当前停在附件06规定的完整镜像许可下载门禁，具体可复核观察见 blocked-witness.json。不是 Docker daemon 故障，也不是预算不足。不能把官方项目许可、签名、镜像摘要或已有G3镜像使用记录解释为本次完整镜像许可已通过。

输入 ZIP SHA256：d9f9e2f90b67a23733d51553a80465862f378664035f11cf83175a1ae636356d。BaseSha：8afc5d4dfd32e7adb48262cce6587057c0e68715；受保护 origin/main：d1a61daffe844475b07705797e3ad325cc3f2945。原33个ZIP条目、Manifest和合同字节保存在 input-original-bytes.json；未把附件历史未授权状态伪写成当前批准。

## 当前可审成果

P0已完成基线/输入/工作树/宿主/镜像manifest及预算核验；完整供应链准入仍BLOCKED。P1公共DTO、API/OpenAPI/TS、权限/状态/Secret/审计/适配器SPI经非作者审查后冻结。PG和UI在独立托管树实施，Master集成，不合main。

P2 DRAFT代码包含真实Npgsql只读Adapter、五类配置表单及PG生命周期页面、Connections独立持久模型与未应用EF迁移、AES-GCM合成凭据存储、短事务审计、Probe预约/恢复、启用前幂等预约、持久Catalog租约/取消和Host组合。非PG表单没有可运行Adapter，不能返回虚假成功。G4仅显式开关且开发环境启用。

P3真实PostgreSQL/OIDC/HTTP从未运行；P4完整交互、重启/撤权/竞态与审计故障验收未完成。P5只交阻塞见证与PARTIAL源码快照，不代表阶段DoD。附件49项完整产品验收均NOT_RUN，独立列于 acceptance-matrix.json。Compose及真实运行/浏览器脚本尚未交付，runtime preflight因此REFUSED；不放置伪造入口来把门禁刷成PASS。迁移仅生成，未连接数据库、未应用/回滚验收。

## 已执行检查及局限

组件检查：G4严格DTO15项、PG Adapter本地负例21项（明确排除RealPgFixture）、UI73项、真实生成TS typecheck通过；Host/测试项目构建无警告/错误。应用状态机源码专项非作者Review发现并修复了Probe同值编辑竞态、同键启用重复源IO、恢复终态覆盖/审计遗漏及ETag格式错误分类。已修复旧Probe失效投影。以上不等同真实并发/事务/安全验收；应用服务仍为未获产品验收的DRAFT。

UI独立Review经历三轮，发现并修复诊断码不匹配，以及userinfo、连接串、URL查询/片段凭据进入sessionStorage的问题。最终Worker Head 99b6158由Reviewer独立Node内存转译复现原反例，写入及旧缓存恢复均不保留合成凭据。所有过程失败保留，不用后续通过替换原事实。

Mac ARM64组件验证；Windows/AMD64原生、全镜像CVE/签名、真实浏览器截图、TLS正反例、真实数据库状态机/事务回滚、完整C#注释语义专项审查均NOT_RUN/NOT_VERIFIED。CI按本地优先政策NOT_RUN。精确结果及退出码以 validation.json 和组件日志为准。

## 资源及恢复

未pull运行镜像、未创建任务容器/网络/卷、未生成实际Secret/PFX。准确before/after及补充image inspect证明原资源保留；首次after漏了--digests造成文本比较false，原观察未抹除，resources-images-recheck.json给同参数与准确ID复验。

本任务6小时上限monitor实际运行约27分钟后向准确PID发SIGTERM并正常exit0，未修改全局电源策略；锁屏/熄屏连续性没有观测，NOT_VERIFIED。临时依赖符号链接只unlink自身链接，保留目标目录。未合main的Master/PG/UI树及分支KEEP，解除条件为独立复审与后续明确集成/证据恢复确认。其余旧G3/G6树、卷、镜像全部KEEP，任务无权回收。

恢复入口：保留当前Master分支，先补准确镜像全部组件许可证据并由非作者准入审查。已批准资源预算与合成Secret策略继续有效，不推断门禁豁免。通过后补Compose/真实launcher并使runtime preflight检查全部消费者，再按P3最短真实PG/OIDC/HTTP→P4→49项稳定完整验收→独立Review/清理/唯一V3顺序继续。不得据此PARTIAL包部署或进入G4-M2。

最终标记：G4_M1_CONNECTION_BLOCKED_WITH_WITNESS。
