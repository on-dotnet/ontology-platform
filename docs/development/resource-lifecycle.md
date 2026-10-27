# 阶段收尾与资源生命周期

每阶段完成且获审后，Master负责项目范围的证据驱动资源收尾。默认读取不等于删除授权；当前阶段用户明确授权的准确、可恢复候选可自主处理，不要求逐个小步骤重复审批。有歧义/不可逆/生产/跨项目项停止对应清理并保留。该制度不能扩大业务阶段授权。

## 归属与分类

任务合同冻结Owner、Reviewer、Base、分支/规范Worktree、owned_paths及公共文件Single Writer。Master唯一集成main；独立写Agent保持独立托管Worktree与任务分支，不能为减少数量改回共用main串行开发。默认只读命令：`pwsh -NoProfile -File scripts/maintenance/inspect-resources.ps1`；Docker明确加`-IncludeDocker`。盘点脚本仅stdout；执行器另用cleanup-resources.ps1，默认DryRun、显式Apply，兼容PowerShell7/macOS/Windows入口，不硬编码用户路径，不读取凭证/env/卷内容。安全cache删除依赖POSIX nofollow描述符，缺能力的平台明确REFUSED/NOT_RUN，不用不安全fallback。

逐资源记录准确ID/原tip、归属依据、阶段/CI/审查、状态、体积估算、风险和动作。状态ACTIVE、KEEP、SAFE_CANDIDATE、AMBIGUOUS、ORPHANED_METADATA；阶段已由人类确认关闭后，不再以无法证明历史聊天不存在一概保留；当前任务/实际锁定、未整合独特提交、具体私有runtime/PFX/唯一证据才构成保留事实，逐项列准确对象和解除条件。Git祖先只是必要证据之一；非祖先需git cherry/稳定patch-id、最终tree/路径差异及PR/提交说明，不能仅凭年龄/前缀/merged列表删除。

## 顺序与边界

1. 开始前status/fetch，保存before清单，保护未提交/未跟踪及ignored私有数据、锁定/活跃树、main和旧Master交接树；不读取其凭证内容。
2. 可验证里程碑commit/push，独立Review，验证实际同Head CI后分批集成main并push。CI无结果是NOT_VERIFIED。
3. Worktree删除只用`git worktree remove <exact-path>`无force，先证明干净含ignored重要资料；成功后完全并入且无活跃引用的本地任务分支才`git branch -d`。远端还须实际tip未变/无开放PR/无跨机器活跃引用/任务已验。非祖先疑义保留。prune只用于确认目录不存在的失效metadata。
4. Docker限本项目测试、无挂载引用、无独有/敏感数据且可恢复的准确ID；至少保留日常开发PG/Jena/RustFS/Keycloak持久数据与固定镜像/必要网络。共享镜像/cache归属未知只报容量，不做全局prune/引擎重置。socket不可用按实际访问错误报告，不将permission denied伪装Engine离线。
5. 旧Review ZIP先核实原SHA/Base/Head/源码blob、不可再生metadata和本地独有证据；保留原SHA，不原地改写。新compact有效且独立重开后才清理准确旧包；原ZIP字节不能重现须明示，但不能丢审批/测试/CI事实。唯一当前ZIP为目标，其他保留项DEFERRED及复查条件。
6. 临时编译产物只在无引用/归属明确时清理；.tools/私有runtime/PFX/.env/证书/卷备份不是普通垃圾。全局codex、其他项目与系统缓存不在项目治理范围。

每动作保存白名单、准确ID、原tip/hash、依据、命令、退出码、前后状态和回收字节。失败不扩大成强删/强推/reset-hard。容量分开报告逻辑/名义分配/真正回收，APFS/硬链接和镜像共享层不重复相加。零安全候选允许零回收，必须解释原因。

G3-M1-001复用执行器时只准本任务已提交CLOSED合成归属证明的`g3-m1-`准确命名卷；不接受该任务的Git/history/image或旧G2卷操作，不用历史任务ID冒充新授权。其它身份守卫保持。新M1托管worker树在独立审查/同HeadCI/集成、ignored元数据及独有证据核验后，使用原生archive_worktree保存可恢复快照再移除；主Master和旧6树保护，私有runtime/PFX不作为普通缓存。

## DoD 与交接

输出实际before/after数量/容量、成功动作、未清理原因和复查触发条件；保留开发环境抽查与工程验证证据。任务/ADR/失败分析/历史Git不删。交接写明确提交、测试/CI/run、恢复入口、未运行平台与新Master开始时动态fetch的origin/main；不让旧SHA成为未来固定基线。阶段结束交一个从已提交Head生成并独立复检的V3包，停在当前复审关口，不自动开始下一阶段Plan或功能。

## 实际清理门禁（PRE-G3-CLEANUP-FIX-002）

已确认安全候选必须按期真实Apply；存在安全候选但实际0删除=FAIL，不能以PARTIAL或统一KEEP/DEFERRED替代整改。仅当准确命令/资源级错误证明不可越过时该项BLOCKED，其它安全项继续推进。所有阶段关闭事实以当前明确授权/验收记录为准，不追索无法取得的历史聊天不存在证明。

执行器：`pwsh -NoProfile -File scripts/maintenance/cleanup-resources.ps1 -Root <本项目干净任务树> -PlanPath <已审JSON白名单>`默认DryRun，须输出具体WOULD_DELETE或拒绝原因；只有明确`-Apply -LogPath <新JSONL路径>`才删除。白名单包含project、仓库Root/commonDir/原始及有效origin、expectedMainSha、带时区created/expires、准确IDs/tips、protectedWorktrees/keep、每项已提交CLOSED合成/可再生证据、cache metadata fingerprint及Docker版本/引用/状态。计划过期、资源替换、脏/锁定/保护路径、PR/外项目/未知私有资料均fail closed。Git远端删除使用准确expectedTip原子lease作为compare-and-delete约束：只收紧已授权删除，不推新commit、不覆盖历史，不使用无条件--force。

默认网络不提供删除操作；全局Docker cache不提供prune。history按具体短Ref/固定builder删除，须保留失败构建摘要；history删除不等于cache释放。保留一套真实可复用开发环境，额外保留须写明准确runtime/PFX/唯一恢复绑定，不以所有测试样例可能唯一为通用理由。闭合且具任务/夹具/归档证据的合成测试组可删除，无需逐条证明合成数据无价值。

新增验收必须包含真实临时Git和mock Docker的safe Apply与拒绝误删、项目实际before/after、逐条删除日志、KEEP集合完整和健康探针或具体限制；ReviewPackage回归不能替代资源回收。公开仓库另做全部可达history/任务refs/已提交证据有限秘密检查；只记录路径/类别，辅助本地refs不自动等同已公开，私有路径metadata-only，不擅自改远端历史。所有未运行平台/语义隐私/任意混淆仍NOT_VERIFIED。GitHub CI必须同Head真实成功才标PASS。

## Build history持久删除门禁

BuildKit v0.34.0的单Ref inspect可能留下零计数引用，使rm仅写内存deleted；列表缺席不能当DB持久删除。当前已审核Buildx0.38.1/BuildKit0.34.0单desktop-linux docker节点：historyBackend计划冻结context/EngineID/bridge generation/完整CLI与server版本/节点；用ref-only列表定位^offset读取原允许字段，必须返回Ref与完整版本指纹吻合。删除后除了列表缺席，还仅接受固定客户端精确的准确ID no-record诊断，deleted/transport/权限/错误Ref一律NOT_VERIFIED/failed。前后generation变化拒绝，raw stderr不输出。旧计划是对应旧提交的历史事实，不能当新工具可重放计划。不得为绕过持久化问题全局restart/update/prune/改内部DB；只在原精确范围重新审查，记录自然生命周期后的实际持久检查。


## CLOSEOUT-002 创建即治理与真实收尾

本轮明确授权处理经逐项归属验证的旧G2测试卷、重复Fuseki image及已关闭history；不复用旧任务身份。创建资源必须登记project、TaskId、RunId、资源前缀/环境、创建时间、canonical image/context哈希、准确ID和恢复入口。历史无label资源以已提交来源和当前metadata交叉证明，不能从名称或<none>推断。

分类为KEEP_PRIMARY_DEV、KEEP_UNIQUE_RECOVERY、SAFE_CANDIDATE、AMBIGUOUS、UNREFERENCED_IMAGE、EXPIRED_BUILD_HISTORY。每个保留对象写准确ID/关联runtime路径metadata/挂载、保留理由、解除条件和复核触发，不复制runtime、env、PFX或卷内容。日常保留一套，其他合成环境以已验证可再生入口或完整可验证备份通过独立审查后清理；私有runtime存在本身不证明全部数据唯一。

Apply必须精确白名单、24h内有效期、实际Engine/context/builder版本与代际、资源指纹、无容器/manifest引用、已提交关闭/合成来源证据及前后逐项日志。逻辑大小、共享层、history metadata、cache、容器stdout与Loki/Tempo卷分别报告，不能叠加显示容量冒充回收。APFS/VM sparse disk没有实测就NOT_VERIFIED。history按现行强无记录诊断并在自然生命周期后再核对；没有发生自然代际时明确NOT_VERIFIED，不主动重启。

验收先隔离fixture真实Docker资源再项目Apply；mock只能验证拒绝路径。必须保留开发环境集合并做健康探针或具体说明限制。稳定Head同CI、唯一默认V3包独立重开后交付；[效率规则](ai-development-efficiency.md)约束新Master和换机器恢复入口。
