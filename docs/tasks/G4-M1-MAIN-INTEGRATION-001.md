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


Run12 / T0ed73cf1a82f73ee3e2be455c431fea1fa978685 在prepare_nuget前误调用R2，被PATH_MISSING拒绝，未启动Restore；原回执保留。相同T的新Run13完成私有依赖准备、R1/R2独立审查、完整严格离线Restore及I01全工程（27套SelfTest376.75秒、36任务测试、native/Web exit0、780总344PASS436SKIP0FAIL、Web379）。I05真实生成链/6负例通过，I03拒绝及注册图部分通过。I02挂载审计已通过，但internal-only网络不发布宿主端口，HTTP_READY_TIMEOUT；容器内Fuseki/RustFS健康200，模块尚未执行，436skip仍0闭合。

本轮仅任务runtime/closeout/migration适配器及tests补精确loopback ingress：固定本机Engine Unix API、准确完整容器ID/Task/Run/镜像/同Run internal网络与IP、低权限Perl透明TCP，32连接、120秒连接期限和4小时进程期限；生产调用路径未改变，未增加网络/镜像/依赖。2MiB真实传输曾发现stdout/stderr跨流EOF乱序，修复后定向通过；真实daemon v3端口冲突/容量/父SIGKILL外部回收/目标已停止回收通过，远端deadline124与子SIGKILL137传播通过。42任务测试及最终19driver独立Review PASS，详见Run13/relay-final-inputs.json。必须再冻结新T/Run完成全流程，不能移用旧T的产品结果；无新V3/main/M2。


Run14 / T4a64070ac6f9be906512d11956252909085e9a8b：R2严格离线及独立后验PASS（21项目168包，5.534秒）；原27套SelfTest368.24秒、42任务测试、native/Web通过，780总344PASS436SKIP0FAIL，Web379。I05 PASS、I03拒绝/DI图PARTIAL。I02正式ingress CLI被runtime早期__main__旧parser拒绝，未执行模块；此前直接daemon诊断未覆盖正式入口，相关可执行性推断撤回。现仅runtime/tests统一底部单入口，两模式实际文件子进程正反及44任务测试通过，独立Review PASS；stub派发测试不是设施/产品PASS。七Docker对象已精确回收，monitor释放；需新T/Run完整验收，旧记录不重写，无新V3/main/M2。详见b-continue-20261104-14/index.json。


Run15 / T897d8fcb7f3111fa8b335370009d51dcf46366b3：R2及独立后验PASS（5.605秒），27套SelfTest370.44秒、44任务测试和native/Web通过；780总344PASS436SKIP0FAIL、Web379。I05 PASS/I03 PARTIAL；I02正式ingress入口及四模块迁移通过，Semantic单进程302案例83PASS219FAIL0SKIP、exit2，记录441次32活连接容量拒绝。新进程同T首失败方法5/5和最大参数化方法19/19通过，但不能据此认定所有219已解释。

任务入口拟仅Semantic采用137精确FQN方法分进程，保留302全部参数化案例及方法内并发；每批Counter精确匹配、无新增容量拒绝、核验占槽/连接/Exec退出后才下一批。原单进程失败保留，不冒充已恢复；其余模块原入口不变。独立复审发现复合耗时解析及核验前占槽盲点，已在任务runtime修复并补正反回归，46任务测试通过；完整分批产品验收NOT_RUN，须新T全流程。原始失败私有日志KEEP，原错误案例名投影保留，另附修正解析视图；无新V3/main/M2。


Run16 / Tf3cc2ce34fb5e083f3e92f4fb8c62d724f388685：R2及独立后验PASS（5.657秒），原27套SelfTest368.57秒、46任务测试、native/Web通过，780总344PASS436SKIP0FAIL、Web379；I05 PASS/I03 PARTIAL。Semantic137方法302案例按方法隔离完整PASS、0容量拒绝，246个原skip已有同T实际PASS见证，但整体fixture closure尚未运行。随后原Publishing单进程78案例31PASS47FAIL、94容量拒绝，I02阻断；首失败方法新进程1PASS仅诊断，全部47原因仍未逐一确认。

任务入口现统一四模块方法隔离：Semantic137/302、Publishing42/78、Query39/49、Agent26/33，共244方法462案例，按(project,case)精确多重集合而非全局去重。保留每方法全部参数、方法内竞争/并发、原外部持久设施以及Agent唯一MCP方法的两次输出；全部模块成功后才Ajv。仅module-tests/tests变更，46任务测试与独立复审PASS；新T完整四模块验收NOT_RUN，旧单进程失败不升级。末次模块资源2.5GiB内存限额、卷106209280字节，未超预算；正在精确收尾后冻结新T，无新V3/main/M2。


Run17 / Ta85b2cf3c40455518fa120359520c3b19a73ac01：R2严格离线及独立后验PASS（5.641秒），原27套SelfTest370.93秒、46任务测试、native/Web通过，780总344PASS436SKIP0FAIL，Web379；I05 PASS/I03 PARTIAL。Semantic137方法302案例及Publishing42方法78案例全部PASS，零ingress容量拒绝；Query前12方法14案例通过，m013在发布的GSP PUT收到500。精确合成诊断PUT实际返回45字节IOException No space left on device，/fuseki 512MiB已100%满，/tmp尚有空间；memory.events max2093/oom0/oom_kill0。保留原失败与私有原始输出，不把无OOM解释为门禁PASS。

仅任务compose.g3/consumer_check/tests调整Fuseki数据tmpfs为1024MiB及内存2GiB，精确限制唯一Fuseki消费者；其余卷上限不变。G3内存5888MiB、模块3584MiB、全部命名卷及匿名tmpfs2820MiB，仍在已批6GiB/3GiB；镜像和JVM640MiB堆未变。46任务正反测试与独立审查PASS，原测试夹具TypeError保留。Run17精确7Docker对象及ingress、宿主monitor、4工具副本已回收，事故KEEP保留；须新T完整验收，扩大容量尚未证明产品通过。无新V3/main/M2。详见b-continue-20261104-17/index.json。


Run18 / Tbaed2f8763dc645858df02add5798fe6ff4f3ec9：R1/R2独立准入及后验PASS，OS全网络拒绝的完整21项目/168包Restore实际5.565秒exit0。I01尚未启动，前置只读审查发现G3→M1切换遗留Fuseki/RustFS两个脱离挂载卷，后续snapshot只统计运行挂载而可能漏算；这不是已观察资源超限。仅任务migration/runtime/tests补准确两卷回收及全部owned卷实测集合闭合，保留平台PG/OIDC及KEEP，删除失败/假缺席拒绝并持久记录。48任务正反测试通过，待独立复审和新T/Run完整验收；Run18恢复不转绑新T，无新V3/main/M2。


Run19 / T648d692684221d39a2cf8ce323254d7ef061e256：R2及独立后验PASS（5.543秒），原27套SelfTest383.06秒、48任务测试、native/Web通过（780总344PASS436SKIP0FAIL、Web379）；I05 PASS/I03 PARTIAL。Semantic302、Publishing78、Query49全部案例PASS；Agent前7方法9案例PASS，第8方法在真实发布准备阶段失败。Fuseki JVM SIGBUS退出127、Docker OOMKilled=false；前测数据卷71%、内存峰值达到2GiB、max197/oom0/oom_kill0，崩溃时最终占用及直接原因NOT_VERIFIED。停止后hs_err复制失败原文保留，不将SIGBUS推定为OOM或满盘。

只读调查证实当前四项目共享一次设施，持续累积持久发布图；旧四drivers各自新建与回收。任务入口修为四固定phase独立三服务寿命，每phase四正式EF迁移、全部原方法/参数及并发、准确资源观测和精确回收；MCP唯一方法输出及全部完成后的Ajv保留。仅任务5文件改动，50任务测试通过，待独立Review和新T完整验收；原失败不升级。Run19 825个Exec实际退出为824×0/1×113，精确7Docker对象、ingress/monitor及4工具副本已回收，KEEP不变。无新V3/main/M2。


Run20 / T7bb08672c354fb97ed39ad4ad7492d2cbe297aad：R2严格离线及独立后验PASS（5.505秒），原27套SelfTest383.26秒、50任务测试、native/Web通过（780总344PASS436SKIP0FAIL、Web379）；I05 PASS/I03 PARTIAL。四模块各自独立设施已实际运行；Semantic302、Publishing78、Query49全部PASS并逐组精确回收。Agent前21方法28案例PASS，m022 SlowSse在HTTP启动前的连续大消息Append失败，后4方法及Ajv/G3整栈NOT_RUN。失败数据库投影显示223次消息后接近10秒lease到期，直接false分支未插桩，不改产品lease或正式断言。

同设施只读SELECT A/B证实任务PG转发12KiB上传中位42.2678ms、24KiB44.0111ms；只为5432设置并读回TCP_NODELAY后分别0.3583ms/0.3936ms。A/B精确helper/实际Perl字节绑定、两实际失败关闭负例及永久五行runtime修复通过独立审查，50任务测试通过；这仍是诊断，不代表正式SlowSse恢复。原失败PGDMP私有KEEP，公开只存SHA/大小/命令；所有28个分阶段Docker对象实际回收（同名卷按CreatedAt世代区分）、全部ingress/monitor及四工具副本已释放，旧KEEP保留。须新T/Run完整验收，I01夹具闭合未运行，无新V3/main/M2。详见b-continue-20261104-20/index.json。


Run21 / T9d865b1335f6b396759533984801405726a0f399：R1/R2独立准入及后验PASS，完整严格离线21项目168包Restore实际5.578秒exit0；尚未启动PREFLIGHT/I01及设施。前置只读核查发现G3跨组织驱动要求operator-a为org-other，但共享bootstrap全部生成org-demo，实际后续必败；不启动无关完整验收。仅任务run/readback/g3-compatibility/tests补原组织真实OIDC→准确realm/user临时切换→全部原兼容断言→原属性/profile恢复→全新OIDC相同subject复验。精确私有原始输入可恢复，进程强杀时保留现场且不宣称恢复。

独立审查提出用户恢复失败会跳过profile恢复，实际负例RED复现后分离两恢复尝试，每项独立记录且任一失败拒绝；共7分支及51任务测试通过。第一次全套因外层sandbox拒绝3本机socket测试而失败，原日志保留，授权本机socket边界下最终通过。此为任务适配验证，不是G3身份真实PASS；须新T/Run完整验收，不转绑Run21 R2，无新V3/main/M2。


Run22 / T3783cdff00ec97e1ed1138549f2b2692587c68f9：R1/R2独立PASS，严格离线Restore5.531秒exit0；PREFLIGHT通过。I01于5.359秒的格式扫描exit1，27套及native/Web/产品门禁未启动。唯一已定位项是Run20原始agent-schema-result.json缺末尾LF；原输出102104字节SHA1fd721a4677ffe0d589609d96ac4db9f75a1bd8bdc811ae8c92843b2641ea51a。无损封装已准备，原件仍保留。自动审批拒绝封装后删除已提交原件，要求明确证据迁移授权，未执行被拒命令；精确申请及原始见证见Run22目录。宿主monitor已释放，本Run未启动容器，四可再生工具副本按独立审查白名单收尾；不构中间V3，不更新main或进入M2。

Run22收尾补充：只读Reviewer调用共享检查器时遗漏禁写bytecode环境，产生本树PyYAML17个pyc/258636字节；原26文件/其余3副本/事故KEEP不变。原四副本计划被INPUT_DRIFT安全拒绝，未删除；Reviewer已撤回无写入声明。新v3准确计划独立准入后实际回收4目录、26858文件/510837724逻辑字节，保留旧plan/失败/副作用证据。Run20原始JSON仍在原路径且SHA不变，证据迁移未获明确批准、未执行。


2026-11-05 用户明确批准Run22精确单文件无损归档迁移。原102104字节、SHA1fd721a4677ffe0d589609d96ac4db9f75a1bd8bdc811ae8c92843b2641ea51a已与已提交封装utf8还原、原Git blob及ignored原件逐字节复核，并实际恢复到本任务ignored见证。仅移除当前树Run20/agent-schema-result.json旧路径；原blob/提交/ignored输出及提案封装均不改字节，恢复映射与执行回执见Run23/archive-migration-applied.json。原Run22失败不升级，后续冻结新T继续完整验收；main/M2未授权。


Run23 / T1abf641d5f5f45356561bccb4c262ef573a738ef：已授权单文件无损迁移后，R1/R2独立PASS（Restore5.836秒），原27套SelfTest398.432秒exit0、51任务测试、native/Web通过（780总344PASS436SKIP0FAIL、Web379）；I05 PASS、I03 PARTIAL。四独立模块Semantic302/Publishing78/Query49/Agent33全部PASS，正式SlowSse及MCP正反也通过。I01仍等待全部适用fixture逐案闭合。

G3六容器真实OIDC跨组织切换及finally恢复通过；首个缺CSRF POST实际500而非403，I02停止。已核实任务配置向产品构造器提供Docker DNS地址，违反既有loopback约束。只修runtime与任务测试为G3数字loopback及Web/API共享命名空间两固定内部映射，M1不新增G3服务；53测试通过。现有夹具短诊断两operator均由500变403 csrf_rejected、两内部健康200，随后原配置精确恢复、代理PID/端口释放；诊断不提升原T的I02结果。须新T完整重跑。

本Run四模块28个分阶段对象及G3后续12对象均已准确回收、KEEP3网络8卷不变，宿主monitor/ingress已释放。四可再生工具副本26919文件512583866逻辑字节已按独立审查v5准确清单删除；两个node_modules残留系统VM只读FD，冻结PID/出生/完整路径/553条只读FD集合且零容器后有限准入，不操作VM，物理空间及FD回收NOT_VERIFIED。事故目录、私有原始日志、归档恢复映射均KEEP。原失败与首次清理拒绝不改写；无新V3/main/M2。详情见b-continue-20261104-23/run-summary.json与公开产物索引。
