# AI 研发效率与交付规则

现行规则由最新人类授权限定；[本地验证政策](local-validation-policy.md)优先，系统/平台安全边界不变。历史任务证据与授权保留原字节；历史版本可从Git恢复。本页统一当前规则，不要求恢复时重复读取整段历史会话。

1. **Preflight-first**：fetch并核对任务Base、工作树/活跃引用和owned_paths。先核对工具、当前平台锁闭包、MSBuild SDK resolver、真实入口及资源准入，再运行CLI。缺前提写BLOCKED/NOT_RUN，不安装下载或改全局PATH/SDK/Docker/WSL来补齐。
2. **规格驱动与先合同后并行**：唯一A–F/合同中的重要要求关联AC-ID、正反Given/When/Then、实现/测试位置、最早验证时机、原件与输入；使用[任务模板](../tasks/templates/sdd-task.md)引用规格，不复制三套spec/plan/tasks。覆盖表不代表测试通过。冻结共享边界、正反例与路径所有权后，按可观察行为纵向切片；先贯通最短真实高风险路径，不等数据库/服务/UI全部完成。作者Review前核AC→实现→用例→原件缺口，非作者早审首条高风险切片并最终集中Review，修正只审增量，不隐藏实际缺陷。共享工程配置Single Writer；独立作者独立托管Worktree，Master只在明确批准下集成main。按独立写项拆分，不为小格式修复反复派新团队或逐patch审批。
3. **分层测试与真实边界优先**：以[gate登记](verification-gates.json)规划静态/单测→相关集成→短真实烟测。默认按程序集/夹具组批量执行。必要要求最终由FRESH或有效REUSED覆盖，才称适用完整验收；不是每Run从I01重开整链。原显式Full命令不缩减；稳定工程输入一次有理由的完整SelfTest，之后纯说明/证据变化不重跑产品。
4. **持续集成**：可验证里程碑提交、普通push任务分支。main由Master唯一集成且必须另有当前授权；任务授权禁止main时停止于任务分支。CI按需，已跑记录真实run/job/Head；未跑NOT_RUN，不将本地PASS冒充CI或其他平台成功。
5. **证据分层**：每个原始日志/二进制保存一次，摘要引用SHA/Git blob。一个当前状态保存目标/非目标、Base/Head、环境、门禁状态、失败指纹和下一动作。失败保留命令/真实exit/短窗口/复现入口；不向上下文塞全部日志。代表截图默认≤12张、PNG目标≤3MiB。
6. **按阶段交付冻结**：依[PLANS唯一阶段表](../../PLANS.md#阶段交付唯一表)执行；产品实施完成默认源码/格式→适用测试→非作者Review→提交→当前输入绑定→唯一[V3包](review-package-spec.md)→非作者独立重开→包外回执，无需再次申请打包，具体用户例外优先。P0禁包只约束P0；纯规则增量引用原包与已提交diff，不重打产品包。先预检格式、身份、规模、argv及证据Schema；最终diff-check必须exit0。正常迭代不产中间PARTIAL ZIP；>10MiB解释构成，>15MiB先去重复而非提限，历史V1/V2仍可重开。
7. **真实效率数据**：复用`task_run_timeline.py` schema2记录真实UTC/单调耗时/exitCode，timingStatus独立。分列首次真实链路形成时点、失败分类及发现阶段、运行次数、无理由restore、未变产品重跑、封包重试、证据处理时间、完整SelfTest、复用与拒绝重复失败次数、证据体积；父子命令计时不相加。未观测的Agent活跃/等待是UNKNOWN，未运行NOT_RUN，无法验证NOT_VERIFIED。规则落地不证明已提速；下一实际任务观察上述数据后再评价，不能为填指标回溯补跑本任务。
8. **阶段资源收尾**：创建即记录TaskId/RunId/准确ID/内容键/恢复入口。环境缓存寿命按任务/依赖键，Run失败不删重建。每Run独立fixture与输出，禁止把临时数据库放bin/obj。只停不需要的自身服务；关闭后按[生命周期](resource-lifecycle.md)准确白名单/期限/指纹/前后证据/强后验回收。安全候选存在却0删除FAIL；每个KEEP说明对象、理由、解除条件。
9. **防跨会话丢规则**：新Master从当前授权及唯一状态进入，读取本规则、构包合同与生命周期的适用部分。任务refs/证据可以证明来源；不能把不可取得的旧聊天当统一DEFERRED理由。过程证据从精确Git对象恢复，ignored只做聚合清单。
10. **不以速度换安全**：零测试、失败、被跳过或缺原件不能代表产品PASS。真实DB/OIDC/UI/权限/回滚不能由Mock或容器Running代替。禁止全局prune/restart/改DB、未知数据删除、收费调用和跨项目清理；socket不可用不写Docker PASS。

## 最早真实切片与同语义设施

只选本任务适用的最高风险边界。数据库发布类功能先执行“实际写入→新DbContext回读→第二版→旧原件回滚”，再扩展其余页面和反例；切片是Agent自检，不逐步申请人工审批。hash/canonical变更须真实数据库往返验证时间分辨率、精确decimal、null/省略、Unicode/顺序；不可变原身份与当前校验身份分开。旧Release恢复不要求最新Draft正文可读或相同。权限变化覆盖清屏与迟到响应；跨实例容量用独立连接/进程，不用单机内存锁替代。

复用正式composition/DI、DbContext工厂生命周期、provider、迁移、序列化及权限守卫；默认只替换受控端点和合成凭据。确需生命周期/模型等测试替换时记录理由及等价检查，不以不同工厂结果证明产品。测试前核准确对象名、schema、roles、协议和ready，容器Running不足以证明前提。

## 环境准备与运行身份

`workflow.py prepare --task <Task>`核验已批准本地内容，在首次CLI前设置私有CLI_HOME、NuGet/SDK缓存、证书策略和OS网络边界。项目--configfile不能单独约束SDK resolver。缺失/损坏/多余链接拒绝启动SDK，缺资源报精确差异，不隐式下载。

内容键绑定OS/arch、工具/锁/SDK来源；Web另有其Node/pnpm/锁键。工作树路径独立绑定，换树重验路径敏感状态；新Head不自动清空缓存。相同依赖第二次prepare下载/物化/无理由restore为0。共享内容先逐成员验证再复用；node_modules必须重新绑定和验证shim/workspace，bin/obj/.next不跨树无条件复制；私有runtime/凭证绝不跨任务复用。

运行环境键另绑定Docker context/Engine、实际镜像、配方与拓扑。Fuseki仍仅canonical内容寻址构建及已校验共享镜像。跨Run镜像restore/save同路径、精确平台/全输入、load前后身份校验；未知容量拒绝保存，Actions仅现有批准SHA/配额。既有真实cold/warm记录可按输入复用，不为普通开发重复证明。

长验收前 `execution_preflight.py check --milestone <支持阶段>`核对准确audit/DI/消费者。短烟测必须真实OIDC→API→源PG→UI动作及拒绝/取消路径；API重建后核对全部依赖实例与网络命名空间，旧Web不得沿用。新环境/拓扑/权限/会话改变需重测。烟测绑定当前源码与构建产物，静态前置与历史在线状态不替代它。

Mac长任务先`host_continuity.py preflight`，用户能源设置持续有效；有界monitor及电源日志只记录实际锁屏/外屏熄灭/睡眠窗口。不改全局电源、不用-d/-u；单命令caffeinate不能代整会话保证，结束释放自身临时进程。

## 影响、复用和失败止损

`workflow.py plan --base <Base> --head <Head> --output <ignored计划>`绑定已提交候选；`verify --task <Task> --plan <计划>`重新计算计划防篡改。登记源码、测试/预期、驱动/SQL、生成器、配置/锁、平台、镜像/fixture和权限的传递输入；docs/evidence中的可执行文件也是输入，未知高风险路径阻断覆盖声明。

前端组件只使Web/交互失效；I07驱动只使相关驱动/交互失效；共享合同/授权/SDK等传播到消费者；打包器只重验打包/来源/兼容。产品gate未配置当前任务准入执行器则NOT_RUN，不自动启动历史M1整链，也不宣称覆盖。

输入键是内容身份，HEAD/RunId仅审计归属。复用必须重新核验原命令成功、非零有效测试/skip要求、精确Git原件及SHA、相同输入/兼容环境政策、没有推翻结果的新缺陷。`--publish-evidence`输出本任务单份原件，提交后`--reuse <精确Git索引>`消费；输出原T/Run/提交/证据SHA/键/资格命令，executionMode=FRESH|REUSED，与旧status枚举分开。不能把REUSED写成本轮exit0。

沿既有失败记录先分流：PRODUCT（产品语义）、HARNESS（驱动/断言/夹具）、EVIDENCE（解析/映射/归档）、ENVIRONMENT（工具/实例/配置）、EXTERNAL（外部前提）。类别用于决定最小重验，不是新增状态源。先最小复现、记录新假设和受影响范围；驱动/断言/夹具语义变化重跑相关场景；纯解析、显示或路径变化先重核不变原件，只有原件不足或矛盾才定向补测。失败指纹绑定相关输入、构建、平台/环境与错误类别。相同指纹无新条件拒绝昂贵链；`--diagnostic`只允许≤20秒短诊断。连续三次同类失败停止扩写，要求最小复现及机制说明；新相关输入与`--hypothesis`提供修订依据，不是全项目永久失败阈值。只有确认瞬态才有界复测，保留全部结果，禁止跑到绿。

第一份真实输出即走现有公共写入→Schema→资格→`workflow.py package-check`/小样归档预检，检查实际后缀、空白、ANSI、空流、ignored与禁入路径；小样仅ignored诊断，不是正式交付包，不新增执行器或gate。先扫描原字节再用现有无损封装，恢复重核散列，不改原件、不放松扫描；纯显示/路径修复不触发产品重跑。证据生成/修改后用`test-review-evidence.ps1`复用正式Schema检查；包VerifyOnly只验证制品，不代产品测试。准入脚本和规则回归证明边界，不冒充真实服务或资源回收。


## G4-ENG-DELIVERY-002 公共执行与资格

主要工程、环境、构建、M2设施与归档检查复用 `workflow_execution.py`；FailureState身份不含RunId，M2操作入口额外绑定稳定产品/执行输入、真实Engine/context/镜像/工具。只读Git对象、文件散列和宿主策略为轻量例外；服务使用START/READY/END，等待单独记录。记录START未闭合为UNKNOWN；超时分类与真实退出码分列，清理不受测试失败止损拦截。

stdout/stderr原字节仅在任务私有commands目录保留。目录可能包含合成凭据、HTTP会话、pg_dump和服务日志，禁止整体发布。公开原件经 `workflow_evidence.py` 调用现有V3路径和内容扫描后才写入；空/ANSI/异常编码等沿用base64封装，先扫描原字节，恢复后重新核对散列。有限扫描不是完整数据分类。

`workflow_m2_build.driver_layers()`显式登记执行层与资格层；未知驱动拒绝复用。历史资格绑定准确WebHead及原件，不等于当前驱动执行；新runner的TLS/取消策略必须有新短场景覆盖。单纯解释器更新可重新核验不变原件，不能抹去历史失败。自然TTL仅在产品语义和原断言驱动均未变时复用。

锁定Vitest通过JSON报告检查用例及套件级状态。锁定MSTest的实际help没有TRX/JUnit输出扩展，不下载扩展、不伪造机器报告，使用唯一完整一致的MTP摘要兼容入口。当前不消费XML报告，未知格式一律拒绝。Vite及Vitest文件转换缓存分别指定到任务runtime目录，不豁免node_modules正文。
