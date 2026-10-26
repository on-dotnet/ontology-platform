# H1 只读盘点与安全分类

基线fetch后main/origin/main=46c7a6de70b1b97c032b12a19bc27c1c54e70f4c；G2实际CI40283523824双job success，只适用该Head。逐资源清单见git-worktrees-before.json、resources-before.json、zip-before.json；均在删除前保存。Root/Owner受保护路径仅查元数据，不读取PFX/私有runtime/env/卷内容。

## Git / Worktree

当前17树、24本地分支（含本任务）、25远端分支。所有旧远端DEFERRED：未核实开放PR及其他机器引用，不进入远端删除条件，无需为了删除扩大调查。原旧聊天ontology-platform-master依赖g2-readiness-test；g2-master私有运行/PFX和共享pythonlibs也重点保护。其他树含.tools和编译缓存，跨会话引用未知，全部KEEP/AMBIGUOUS，零删除。没有locked/prunable/missing记录可安全prune。

非祖先git cherry：AI0+/17-，FE0+/11-，FINAL0+/1-，HOST0+/3-，OBS0+/4-，PUB0+/10-，QA0+/4-，QRY2+/10-，READINESS0+/1-，SEC1+/9-，SEM1+/22-，G1SEC0+/5-。即便全负号也不据此删除。完整tree OID与最终diff统计保存在JSON；完整树不同。

独立调查的四个非等价patch稳定ID：cee8a7b→e5efd21a9491de015c666d2419d6a929de126b53（guard后续2行差异）；b8dc13c→93e56cbbc55c15d2417607affe454733b199f4dd（QRY四文件129+/4-）；42c95db→cefa11e273a76fd94f59679f1ef4f290caa7281a（涉及路径最终等价）；098418c→5e5950641e174fd694dfc504e0f54e36870a5533（合同后续44行差异）。对应任务卡Master集成回执/independent-integration-reviews/readiness-test-independent-review可追踪，不把历史DRAFT提交直接等同未验收，也不由此断言所有原tip已包含。

主树六个既存DS_Store保留。最初23树，新native树创建后观察17树（七个旧G1记录消失）；原因NOT_VERIFIED，未发出旧树删除/归档命令，不计回收、不访问全局codex调查。名义du合计约4.58GiB，APFS/硬链接共享不能当实际可回收容量。

## Docker / 缓存

首次沙箱拒绝socket，经自动批准只读查询后可达；不能标Engine离线。2 exited容器、48命名卷、3默认网络、23镜像、13缓存记录；逻辑体积镜像5.747GB、容器177.1MB、卷3.772GB、缓存500.1MB。Docker报reclaimable不是数据可删除证据。全部KEEP/DEFERRED，零删除/停止，不执行任何全局prune。

Keycloak exited容器18a8b1844db8没有挂卷，其177MB可写层是否有独有状态未知；PG731a3eb86c2b引用wave2-a5431c01414a-postgres-data；均保留。48卷来自G2/M0/Wave2，历史审计、Run、版本、恢复实验及私有资料唯一性无法证明。三组G2中的ef979bd04cc0有提交运行证据，其余两组准确任务映射NOT_VERIFIED；不只凭前缀删除。默认bridge/host/none及共享镜像、全局cache不触碰。

固定开发版本：PG18.6-trixie、Keycloak26.8.1（身份持久数据在PG keycloak库）、RustFS1.0.3、Jena6.2.0；Alloy1.21.2/Loki3.7.9/Tempo3.1.1/Prometheus3.15.1/Grafana13.2.4。摘要以AppHost/infra现行配置为准。g2-master原私有runtime/PFX留在同checkout；恢复使用现有g2-runtime.py full --runtime-file参数和该树原私有文件，不跨树复制。M0随机卷不是稳定日常开发配置。未重启开发栈，恢复运行NOT_RUN。

## Review ZIP

四旧包共66,387,291字节。逐个sourceMembers原字节与明确Head Git archive/blob全部一致；完整binary patch由固定Base..Head命令重算逐字节一致。非再生检查/CI/日期/环境/审批事实与本地三个M0独有收据已先归档legacy-package-records；原包SHA/metadata SHA、size和恢复策略均记录。庞大manifest的重复source映射与ignored路径清单只保留计数/分类/规范JSON hash，其事实可从对应Head/schema1规则及保留工作树核验；不承诺原ZIP逐字节复造。审批/CI/测试信息不丢失。

四ZIP仅SAFE_CANDIDATE，必须在本轮已提交轻量包成功构建且独立重开后才允许准确路径删除。新包失败时保留全部旧包。三个M0本地JSON已归档后可按确切hash删除；DS_Store不读不删。ZIP目录最终如保留文件，必须写DEFERRED及理由。
