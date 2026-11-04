# G4-M1-MAIN-INTEGRATION-001

状态：B / BLOCKED_WITH_WITNESS；P0限定准入通过；稳定产品验收未启动。

最新用户授权：按2026-11-02 Plan审查执行授权执行。原始审批见本任务证据p0/original-documents.json 中的 approval-original.md；完整计划见G4-M1-MAIN-INTEGRATION-001/PLAN.md。

ApprovedMain=d1a61daffe844475b07705797e3ad325cc3f2945；CandidateSourceHead=99753df6f03b184e40b431a5b5aba89d8fa67087；TaskBranch=codex/g4-m1-main-integration-001。Master唯一作者与共享输入责任人，非作者Reviewer只读。

owned_paths：计划第2节精确任务文档、证据、experiments/g4-m1-main-integration所列文件及PgFixtureSecurityTests.cs两处精确身份白名单。read_only_dependencies：其余产品Host、Contracts、Modules、UI、migrations、生成器/产物、共享scripts、CI、锁、历史证据及旧工作树。公共合同无变化。

只复用核验本地工具/镜像，零下载、零费用，最多6容器/6GiB，卷3GiB观测停机阈值。原49产品检查保持INHERITED_NOT_RERUN；CI/Windows/Intel NOT_RUN；AMBER-A1和完整供应链限制保留。

严格停止：任一产品缺陷需越界修复、工具/镜像身份不符、输入漂移或资源边界失败时保存见证并停止对应入口。最终B交唯一LOCAL V3与包外回执，只有全I01-I08和独立Review通过才READY_FOR_CHATGPT_MAIN_MERGE_APPROVAL；不得执行C/main更新或M2/G6。

具体阻断、未完成适配和精确修复申请见 [阻断交接](../evidence/G4-M1-MAIN-INTEGRATION-001/blocked-handoff.md)。本次任何提交/ZIP只交付阻断见证及DRAFT，不代表B完成；不授权C。

## 2026-11-03 精确格式补丁续执行

最新明确授权为精确15文件格式/BOM追加审批；独立源码提交80af5bb3a5c6cbe3906bb6aee8a78c2bc7536f7e，15/15校验并普通推送。原owned_paths仅追加该审批表的精确字节例外。whitespace通过、完整format仍exit2，新T SelfTest初始扫描exit1，状态保持BLOCKED_WITH_WITNESS。当前结果和未应用三文件最小申请见[本轮阻断交接](../evidence/G4-M1-MAIN-INTEGRATION-001/resume-20261103-01/blocked-handoff.md)。旧证据/ZIP原样保留，三文件提案未授权未应用。

## 2026-11-03 三文件精确修复结果

精确三文件补丁已完成，源码提交2b5af7b81fbd78143ea2a76c787bfc2fa402e30d；新T8c7e43ab4f8f27d231d9d83b42c96ef17a1918fe额外无损归档旧空日志。完整format、build、27套SelfTest、双扫描器正反与编译迁移ID检查通过；直接受影响两项目79通过/260真实夹具跳过/0失败。详见[本轮交付](../evidence/G4-M1-MAIN-INTEGRATION-001/three-file-apply-20261103-01/handoff.md)。仅三文件修复及必要证据/收尾；B整体验收未完成，适配器DRAFT和I02–I07未运行，不进入main审批或M2。此前段落保留当时状态，旧空日志按新归档映射恢复原字节。


## 2026-11-04 阶段 B 消费者续执行

最新用户指令为执行 2026-11-03 PHASE-B-CONTINUE，原文和SHA归档在 [本轮证据](../evidence/G4-M1-MAIN-INTEGRATION-001/b-continue-20261104-01/index.json)。恢复Head为720c9cb72a22b9d905a1adade65c042de79a5ad0；恢复时工作树干净，远端main/任务分支与批准值一致。已审三文件和旧ZIP保持原字节。本轮RunId=b-continue-20261104-01，Master唯一作者，Reviewer只读。

19项精确白名单任务消费者/配置已补齐为可执行草案：统一身份及输入绑定、离线工具副本、真实工程/生成链/Host/模块/迁移/HTTP/浏览器门禁、源数据库读回、故障恢复、精确回收和离线main竞态fixture。所有产品文件、共享脚本、锁和CI继续只读。边界16项测试通过；这不代表真实产品验收通过。

B0独立审查及新T尚待冻结，I01–I08本轮均NOT_RUN。执行顺序保持B0→T→I01→I05→I03拒绝→I02→I04/I03正例→I06→I07→I08；依赖缓存缺失、真实产品失败、输入漂移或超预算时停止依赖步骤并保留见证。此前阻断和PARTIAL交付段落保留历史时点，不作为本轮通过依据。当前仍不授权main/M2/G6，不生成重复中间ZIP。

B0补充独立审查通过，最终19项驱动清单SHA21c6b08b1246a16c501f1148269d5a18e822af93d66d7807ac702a378d7e1a73，17项边界测试exit0，无开放P0/P1/P2。获准沿用既有B授权冻结新T并开始PREFLIGHT/I01；真实产品门禁仍NOT_RUN，不将本审查当作B完成。


## 2026-11-04 真实 I01 与离线边界事件

新T e09a8c8fc7f21ac1f3d447e8f67493c5f85059f0上原SelfTest27套和任务17项通过；全solution restore失败，后续原生/Web/产品门禁未运行。本任务入口漏读Mac专用锁，SDK解析还绕过项目离线源产生NuGet HTTP缓存；原始事实保留，零下载门禁未满足。此前B0/PREFLIGHT的边界充分性结论被真实运行推翻，不能据此继续标PASS。

四个任务工具完成修复，168锁包本地只读核验、SDK/OS/首次运行隔离probe及22任务测试通过，非作者修复Review通过；尚无修复后完整新T验收，保持BLOCKED_WITH_WITNESS。详见[阻断与恢复交接](../evidence/G4-M1-MAIN-INTEGRATION-001/b-continue-20261104-02/blocked-handoff.md)。仅收尾证据与已审安全副本回收，真实门禁停止，无新V3/main/M2。

本轮安全回收已实际完成并独立后验：9目录、30,324文件、1,058,341,260逻辑字节；旧事件CLI目录和历史包KEEP。最后补充按Run隔离CLI_HOME，23项任务测试与只读Review通过；真实门禁仍停止，修复后完整新T未运行，最后Head见包外回执。

## 2026-11-04 严格离线恢复续执行

最新明确授权为 OFFLINE-RESTORE-RECOVERY-20261104，原文及SHA见本任务 b-continue-20261104-03/r0-initial.json。原Head 00c6f472c40bbe75d7b577a6144ca6046221a5d4，ApprovedMain不变；Master唯一作者，Reviewer只读，产品/正式测试/共享配置继续只读。R0身份及168锁包+两个额外SDK输入已核验；R1补齐每Run独立CLI/packages/HTTP/scratch/temp、实际SDK预处理导入、OS拒绝网络/全局写入、空缓存及解包字节验证、审查回执防跨Run重放。29任务边界测试通过，不代表完整Restore或产品通过。

本轮顺序为R1独立Review→新T→全新Run R2完整solution严格离线Restore→R2独立Review→PREFLIGHT/I01及原有后续门禁。旧事件目录只读KEEP，旧失败与外联实际字节NOT_VERIFIED不改写；260历史跳过仍0项被本轮关闭。全程不更新main，不进入M2/G6，失败不重复构中间V3。

新T e14cb8c60535ef28b3f99c511de5954eecdef693的Run04完整Restore在项目枚举处停滞，精确终止后dotnet实际exit0，但资产来源后验拒绝，R2=BLOCKED。单/双节点短对照证明相同OS断网边界下单节点21项目枚举正常，双节点5秒超时；连接目的地仍NOT_VERIFIED。任务入口仅追加-m:1及显式终止标记拒绝，待补审冻结另一新T后使用新Run复验；原失败原始字节已保留，不混作Restore PASS。


Run07 / T d5c7a9f9eba2f9025e19cc38c10b36f58d53545c 的完整严格离线 Restore 已 exit0，21项目资产、168包与两个SDK实际来源核验通过，独立R2 Review通过。该结论仅绑定Run07/T；其后I01原SelfTest在HostContinuity临时输出边界测试失败，native/Web及真实后续门禁未运行。原始失败与R2见证见 b-continue-20261104-07。任务临时目录现移至本Run私有.tools目录并登记manifest；正式测试保持只读。同时任务适配器补齐按参数逐案闭合、真实模块迁移/Security/OIDC/V2输入、审计旧行集合、凭据DB见证和UI精确故障映射。新批次仅针对性验证，须独立Review、新T、新Run R2及完整I01后再继续。任何歧义SKIP拒绝闭合；旧260项本轮仍0已闭合，无新V3/main/M2/G6。

Run09 / T43f18e80d769bc0eea6373cbd40252e988fa6233：严格离线R2及独立后验PASS；原27套SelfTest exit0（382.874秒）、33任务测试通过。.NET build/format和8项目正式测试完成：780总计、344PASS、436SKIP、0FAIL；保留已有ASPIRE010警告。原完整I01因复制pnpm workspace状态仍指向旧树而在Weblint前失败。所有436跳过逐案唯一映射，历史260包含其中，0已闭合。仅改变本树ignored副本路径记录并丢弃旧validation缓存后，原pnpm强校验及Web lint/typecheck/379测试/build针对性通过；原失败不改写。任务入口现固化精确重定位/重新验证，34任务测试通过，待独立Review/新T/新Run完整验收。详情见b-continue-20261104-09，无新ZIP/main/M2。

Run10 / T636c7b46924f8e09d98cd915fa9dcb7cb226ffbe：R2及独立后验PASS，PREFLIGHT含pnpm重新验证PASS。原27套SelfTest exit0（372.156秒）、34任务测试、完整native/Web及8项目Detailed全部完成，780总/344PASS/436SKIP/0FAIL，Web379测试通过；I01 PARTIAL等真实夹具逐案闭合。I05先因外层桌面沙箱导出未完成而精确停止（actual -15），同构建明确loopback环境0.2578秒短导出成功；原生成链正例及客户端再生比较通过，但枚举负例错误假定顶层enum导致NEGATIVE_SCHEMA_MISSING。仅任务验收器改为精确PG type属性枚举、补实际合同正反测试并为导出加显式外网deny/loopback及30秒期限。35任务测试和6个负例短回归通过；仍须新T/新Run完整验收，原I05不改写，无main/M2/新V3。


Run11 / Tbf7fb4719a1ec7084076c7f7ff16c3ddf43f5269：R2及独立后验PASS，27套SelfTest、35任务测试、完整native/Web通过；780总/344PASS/436SKIP/0FAIL，Web379。I01 PARTIAL，436夹具跳过仍0关闭。I05真实生成链及6负例PASS；I03四启动拒绝及六实际DI图PASS，正例未闭合。I02创建三模块容器后因Docker Desktop bind Source带/host_mnt前缀触发PATH_BOUNDARY，尚未模块迁移或测试；精确7资源实际回收及独立后验PASS。任务检查现按实际Compose声明精确接受native或对应Desktop映射，36测试与已保存实际Mounts重放通过，并补RustFS有界就绪等待；URLError底层原因未验证。须新T/Run完整门禁；旧结果不移用，无新V3/main/M2。详情见b-continue-20261104-11。
