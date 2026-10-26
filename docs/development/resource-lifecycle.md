# 阶段收尾与资源生命周期

每阶段完成且获审后，Master负责项目范围的证据驱动资源收尾。默认读取不等于删除授权；当前阶段用户明确授权的准确、可恢复候选可自主处理，不要求逐个小步骤重复审批。有歧义/不可逆/生产/跨项目项停止对应清理并保留。该制度不能扩大业务阶段授权。

## 归属与分类

任务合同冻结Owner、Reviewer、Base、分支/规范Worktree、owned_paths及公共文件Single Writer。Master唯一集成main；独立写Agent保持独立托管Worktree与任务分支，不能为减少数量改回共用main串行开发。默认只读命令：`pwsh -NoProfile -File scripts/maintenance/inspect-resources.ps1`；Docker明确加`-IncludeDocker`。脚本仅stdout，不提供Apply/删除入口，兼容PowerShell7/macOS/Windows，不硬编码用户路径，不读取凭证/env/卷内容。

逐资源记录准确ID/原tip、归属依据、阶段/CI/审查、状态、体积估算、风险和动作。状态ACTIVE、KEEP、SAFE_CANDIDATE、AMBIGUOUS、ORPHANED_METADATA；无法确认跨机器/旧聊天引用时保留，给复查触发条件。Git祖先只是必要证据之一；非祖先需git cherry/稳定patch-id、最终tree/路径差异及PR/提交说明，不能仅凭年龄/前缀/merged列表删除。

## 顺序与边界

1. 开始前status/fetch，保存before清单，保护未提交/未跟踪及ignored私有数据、锁定/活跃树、main和旧Master交接树；不读取其凭证内容。
2. 可验证里程碑commit/push，独立Review，验证实际同Head CI后分批集成main并push。CI无结果是NOT_VERIFIED。
3. Worktree删除只用`git worktree remove <exact-path>`无force，先证明干净含ignored重要资料；成功后完全并入且无活跃引用的本地任务分支才`git branch -d`。远端还须实际tip未变/无开放PR/无跨机器活跃引用/任务已验。非祖先疑义保留。prune只用于确认目录不存在的失效metadata。
4. Docker限本项目测试、无挂载引用、无独有/敏感数据且可恢复的准确ID；至少保留日常开发PG/Jena/RustFS/Keycloak持久数据与固定镜像/必要网络。共享镜像/cache归属未知只报容量，不做全局prune/引擎重置。socket不可用按实际访问错误报告，不将permission denied伪装Engine离线。
5. 旧Review ZIP先核实原SHA/Base/Head/源码blob、不可再生metadata和本地独有证据；保留原SHA，不原地改写。新compact有效且独立重开后才清理准确旧包；原ZIP字节不能重现须明示，但不能丢审批/测试/CI事实。唯一当前ZIP为目标，其他保留项DEFERRED及复查条件。
6. 临时编译产物只在无引用/归属明确时清理；.tools/私有runtime/PFX/.env/证书/卷备份不是普通垃圾。全局codex、其他项目与系统缓存不在项目治理范围。

每动作保存白名单、准确ID、原tip/hash、依据、命令、退出码、前后状态和回收字节。失败不扩大成强删/强推/reset-hard。容量分开报告逻辑/名义分配/真正回收，APFS/硬链接和镜像共享层不重复相加。零安全候选允许零回收，必须解释原因。

## DoD 与交接

输出实际before/after数量/容量、成功动作、未清理原因和复查触发条件；保留开发环境抽查与工程验证证据。任务/ADR/失败分析/历史Git不删。交接写明确提交、测试/CI/run、恢复入口、未运行平台与新Master开始时动态fetch的origin/main；不让旧SHA成为未来固定基线。阶段结束交一个从已提交Head生成并独立复检的V2包，停在当前复审关口，不自动开始下一阶段Plan或功能。
