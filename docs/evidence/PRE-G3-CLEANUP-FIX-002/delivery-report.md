# PRE-G3-CLEANUP-FIX-002 实际整改交付报告

Mac资源治理实施范围已完成，266个唯一资源的实际回收已经成立；资源变更命令共284次尝试，568条before/after。原18 history只有内存删除标记的缺口已修复，并经实际自然VM新代际复核没有回现。独立审查/验证与最终交付门禁见下文。状态为READY_FOR_REVIEW / PARTIAL：Windows/Intel/生产、语义隐私/任意混淆、共享BuildKit项目独占归属和macOS物理空间仍未验证；不是以PARTIAL替代安全候选删除。不修改G2业务，不进入G3。

BaseSha为de2c020c486df5557b1b17f6b62c1befd96312f2。C3实际同Head b9322e599aabac6fac8ed8a6f4ceeae767d1323b在run40355496041两个job success后Master快进main并push，再fresh DryRun和Apply。最终已提交Head与真实同Head main CI由ZIP manifest/git-ci及外部delivery-receipt记录，避免把未来CI/包散列写入产生它自身的Git提交。

## 真实Before/After

Git使用Apply前实际26/28/16；初始24/26/17之后增加本轮两个任务枝，g2-ai一棵树在任何Master Apply前外部消失并撤回31操作，不计本轮回收。Docker列初始数和恢复探针增量，preApply及live-after快照另完整保留，不能只减计数。

|类别|Before|安全候选|实际删除|After|容量变化|未删除的具体原因|
|---|---:|---:|---|---:|---|---|
|Git本地分支|26|11|11|15|refs，无物理字节承诺|main/当前任务/G2 Master+12非祖先原始refs，逐tip/cherry/路径差异在风险矩阵|
|Git远程分支|28|13|13，逐tip lease compare-and-delete|15|refs，无历史重写|main/当前任务/G2 Master+同12非祖先恢复refs；无开放PR|
|Git Worktree|16（初始17−外部1）|10|10，正常remove无force|6|175 cache逻辑2,530,247,461 bytes；10树du名义2,898,540KiB|主checkout/当前Master/G2 Master私有资料及QRY/SEC/SEM独特补丁|
|Docker容器|初始2；探针+9→preApply11|2历史停止容器|2历史；另9本轮探针由可信AppHost正常退出|0|旧停止层177,119,232 bytes；探针增删不计历史节省|无遗留停止/运行容器；24数据卷保留|
|Docker卷|48|24|24|24|候选原逻辑1,939,386,960 bytes；Engine总用量净减1,931,199,733 bytes|3套G2实际私有runtime/realm/PFX绑定，每组8卷；ef979选定实际可复用|
|Docker镜像|初始23；探针+1→preApply24|13|13|11|Engine layer计数净减59,256 bytes，不能累加13×503MB|10固定/最新基线镜像+1此次恢复精确构建镜像，均完整列ID|
|Docker Build history|初始18；探针+1→preApply19|18|18唯一记录持久删除；原18瞬时删除后重试18，不能算36回收|1|仅记录删除，不虚报cache释放|保留本轮恢复构建记录；原失败摘要归档，跨自然代际旧18无回现|
|Docker Build cache|13|0项目独占候选|0|13|CLI Total约500.1MB未变|13记录共享，无法证明按项目独占；未运行任何全局prune|
|Review ZIP|1旧有效包|1，交付后置|仅在新包独立成功重开后按精确hash删除；最终实际值见交付回执|目标新1|旧包2,021,459 bytes；新包实际size/hash由回执记录|旧包在新包未验前保持；唯一runtime元数据/原交付收据已归档|

容量均为lstat文件长度/du名义分配或Docker Engine所报告逻辑用量。卷净下降小于候选逻辑和，是保留环境启动后自身写入增长；镜像共享层实际几乎不释放。APFS clone、Docker sparse disk与macOS物理磁盘回收NOT_VERIFIED，以上数字不能相加声称物理释放。

## 精确执行和保护

- 原审核297操作撤回外部已消失g2-ai的30 cache+1 tree后冻结266。实际Apply计划SHA256 1ee60b336c3eb823bd2d8b5db0f41845b08f99d6432805e4d7162a59c22cc0d4；资源/保护规范hash a93aa9b012b86e7faa899eb2f87d326b2b34851b555a363fa9408e1e8c2cca40。过期8h，任何身份/引用/根/有效URL/tip变化拒绝。
- fresh默认DryRun exit0，validated266/completed0。初次Apply exit0、validated266/completed266；原532行与SHA256 ca45ef67c680c7bdf0feeef2cdec0714bcc4fea1e2602af4a5176e3f65b75e5e原样保留。其18history当时list缺席但在自然VM更新后回现，持久完成结论及时撤回，未篡改旧日志。修复e40b1be在CI40365150329同Head双job success后main快进；仅原18子计划fresh DryRun0，再Apply18/18 exit0，新36行SHA256 3c2faa57f3303875c82c0f4dadebae26ca74b3552da28d436b908f3e4b835fb1。两轮共284资源变更命令尝试、568行，唯一有效目标仍266。
- 缓存只精确可再生路径，9根symlink只unlink不跟随；3个旧小测试证据先原bytes归档。31,000项依赖树的逐文件核验耗时较长，未绕过安全删除。没有删除整个ignored集合。
- 原G2三组24卷与3套私有runtime/PFX全保留，原12非祖先分支保留；QRY/SEC/SEM的真实独特补丁与后续限定处理建议逐项在retention-risk-matrix和原Git完整patch-id/diff证据。安全祖先、干净等价旧工作目录和合成Docker组全部实际执行，无统一DEFERRED代替清理。
- 默认bridge/host/none完整ID在preApply→afterApply→可信shutdown严格相同。初始docker-before→preApply曾观测bridge ID外部漂移（210e…→de218…），原因NOT_VERIFIED，发生在Apply之前，不归因或静默修复；532日志无网络命令。探针只创建并正常释放自己的Aspire会话网络。

## 复用开发环境与恢复入口

选定已存在g2-ef979bd04cc0合成数据组为日常复用环境。8个准确卷和10个固定镜像ID/摘要在approved-candidates keep；另两组因G2 Master真实私有runtime/realm/PFX绑定保留，无独立完整备份/替代方案。不是把48个测试卷都称为固定开发环境。

在保留的g2-master树使用已验收wave2-runtime.run(existing runtime, full, g2, Release)，只在内存由可信运行器消费原配置，不prepare/bootstrap、不打印/复制私有值；入口复现见reuse-probe-entry.py。清理前及初次Apply完成后的T1：PG pg_isready exit0、Jena /$/ping 200、RustFS /health/ready 200、Keycloak管理/health/ready 200，8/8总探针通过。随后核PID/UID/entry只SIGINT本轮launcher，实际exit0，9容器/自建网络正常退出，24命名卷保留。后续仅18条history元数据纠偏不涉及开发数据；未为跨VM复核再次启动AppHost。只验证T1资源健康与最终保留集合，不声称当前服务仍运行、重新做G2业务/E2E或生产HA验收。

## 质量、公开history和交付边界

清理器40项真实tmp Git/mock Docker（原35基础上新增5项持久删除回归）、history扫描器9项、Inspector9项与既有ReviewPackage54项独立存在；C3本机SelfTest及同HeadLinuxCI实际成功，cleanup_review/package_review/public_history_review独立发现并推动修复的全部C/I/M已关闭。不能把54构包测试冒充实际清理；实际两轮568日志、18强DB无记录诊断、跨代际持久复核与集合差另见actual-reconciliation.json。最终独立实际Review和本机/CI以各自实际回执为准。

C4在b932独立覆盖289 commits、2235 blobs、46,825,908 bytes；修复e40复扫290 commits、2278 blobs、48,032,661 bytes、零遗漏，原6命中均与初始triage相同：变量/随机生成表达式、Docker host合成fixture，not_actionable（高置信度），无新增真实外泄或需轮换项。本地Codex辅助refs不证明已公开；不读ignored/private bytes、不改Git历史。有限模式不等于不存在所有机密，语义隐私/任意混淆/未取远端对象未验证。

唯一V2 compact包只由最终已提交Head生成，全部现行非证据源码/本任务证据各存一次，完整patch与blob索引保持，不修改已验收构包器。旧包源码/差异Git可恢复；原包byte-identical重现不保证，所以唯一runtime manifest/CI/status/checksum/summary及完整收据先归档。最终CI和ZIP重开、旧包精确unlink是提交后的运行事实，保存在最终同Head交付回执，不伪造自引用Git证据。交付后停等本关口复审。

## 后验history缺口的完整闭环

BuildKit v0.34.0的单Ref查询会留下零计数键，删除可能只设置内存deleted，列表因此假缺席。官方固定tag源码机制已双人独立核对，与本次VM更新后原18回现现象吻合；未读取私有DB或内存，具体内部执行路径属于有证据支持的推断。e40工具使用ref-only列表定位^offset，严格返回Ref/fingerprint匹配；historyBackend冻结已审核Buildx0.38.1/BuildKit0.34.0单节点及Engine/bridge代际，rm后只接受准确ID的精确无DB记录诊断，内存deleted/transport/错误ID/后端变化均failed。无新依赖、RPC竞态、全局restart、update、配置修改或DB编辑。

实际新代际准备：首个blankRef BuildKit RPC前VM0、后VM1，bridge由0c594…变为48a09c…；原18元数据和指纹完全相同，正式计划SHA256 8cbdd24b9af0340a2430ac5af1f3757e7a270c73de622f446ea831bc556e7bbd，独立门禁C0/I0/M0后才执行。18强无DB记录诊断全部通过，after仍0containers/24vol/11images/1history。

随后暂停所有本机Docker API/streams超过6分钟；首个blankRef请求后再次实际VM0→1，bridge变为212a7e664296e138afac7ddbdbc7a070bcc09291cffde470914c4c62189a8b35，旧18全部未回现，仍只保留本轮恢复记录。Engine/CLI/context保持一致，最终资源集与原保留集合一致。见history-persistent-check.json及docker-final.json。自然生命周期触发可能是Resource Saver，但指定设置投影未取得值，触发原因不冒称已确定；没有主动重启/改默认网络。原始快照、回现纠正、官方根因、RED/GREEN、两轮日志、强诊断和自然代际持久复核均保留。总量不把重试重复计算。
