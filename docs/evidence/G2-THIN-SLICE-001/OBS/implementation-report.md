# G2-OBS-SUPPORT 实施交接

状态：READY_FOR_INDEPENDENT_REVIEW / DRAFT / PARTIAL。仅collector边界通过，独立Review、Master产品Meter E2E及最终集成CI待执行；未声明G2整体PASS。

## 范围与提交

- BaseSha：216ea75b7a10fceab35842ba5fa6f509e891bef6；开工fetch成功，origin/main=6154ebb3703031a49cf0c555c9f0c3596e3b7726，任务树HEAD=Base。独立树g2-observability，分支codex/G2-OBS-SUPPORT；只按当前授权与G2-OBS-SUPPORT任务卡。
- 源码提交：aad7a0aac0eb04a99a3eedbc171e9ba30210c11e，DRAFT，待Master集成；证据提交为包含本文的后继提交。
- owned_paths仅infra/observability/alloy/config.alloy、scripts/acceptance/g2-metric-boundary.py、本文所在OBS证据目录。没有修改Host/业务/既有测试/共享监控资源/依赖/锁/凭证。项目ignored .tools/pythonlibs仅链接Master现有PyYAML6.0.3，不安装依赖。
- 仅metric datapoint增加5个键、28个精确固定值；逐键删除其他值。原HTTP键和resource service.instance.id保留。官方Alloy fmt格式化整个owned配置；[范围对比](scope-verification.json)证明metric块外仅空白差异、日志/Trace所有OTTL语句相同。

## 从源码核实的有限值

| 键 | 精确值 | 发射依据 |
| --- | --- | --- |
| capability | describe_ontology, resolve_entity, traverse_relationships | CapabilityRegistry.Create三项定义；SemanticGateway.ExecuteAsync传入已Resolve能力；89510fe的AgentRunExecutor/ExecutionRunService仅已注册能力 |
| status | Found, Empty, Partial, Unavailable, Unauthorized, Ambiguous, allowed, failure | SemanticGateway使用Status.ToString()，因此取C#枚举名而非JSON大写协议；PublishingTelemetry的五个固定Record调用 |
| operation | AnalyzeAsync, ValidateAsync, ApplyEditAsync, DeployAsync, VerifyAsync, ReadPublishedAsync, ReadVerifiedPublishedAsync, publish, rollback, outbox | JenaSemanticRuntime.Execute的CallerMemberName与七个入口；PublishingActivation与ReleaseOutboxDispatcher固定字符串 |
| outcome | completed, failed | JenaSemanticRuntime finally；89510fe的AgentRunExecutor两个计数分支 |
| phase | lease, verify, consume, commit, prepare_or_commit | ReleaseOutboxDispatcher/PublishingActivation固定Record调用 |

基线源码路径：backend/src/Modules/Ontology/OntologyPlatform.Modules.Ontology/JenaSemanticRuntime.cs，backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/{CapabilityRegistry,SemanticGateway}.cs，backend/src/Modules/Publishing/OntologyPlatform.Modules.Publishing/{PublishingActivation,ReleaseOutboxDispatcher,PublishingTelemetry}.cs。Agent源码只通过git show 89510fe读取，不从其他树复制源码或凭证。新维度是有限枚举并集，没有开放任意值；未来新增产品值需要显式合同与新正反验收。

## 真实RED→GREEN

[实际调用与退出码](acceptance-commands.json)，[RED原始容器命令/输出](red/result.json)，[最终GREEN原始容器命令/输出](green-formatted/result.json)。所有镜像为既有批准digest，--pull=never。Alloy v1.21.2 digest=sha256:89a5a320168387336b9ac3c850609c3ba7757eadd4ae5f1d819deb35e9854b18；Prometheus v3.15.1 digest=sha256:fa3302279710be2f21a8301ec17a8b4f2301fd829bd113839b3b6b02b6f191a2；本机arm64，Docker29.9.2。

74个合成OTLP数据点，经真实Alloy批处理与OTLP protobuf出口进入真实Prometheus；RED和最终GREEN重放同一JSON载荷，canonical SHA记录在调用证据中。实际查询77条数据series；完整series索引79条，含受清理的target_info。每轮都保存Prometheus原始查询/series与输入。

| 项目 | RED | 最终GREEN |
| --- | --- | --- |
| 28个有限键值 | 0/28 | 28/28 |
| 40个非法值/类型 | 40/40 | 40/40 |
| 4个产品instrument名称/形状 | 0/4 | 4/4 |
| G1 HTTP与双service.instance.id | 2/2 | 2/2 |
| 隐私marker/键/series标签边界 | 3/3 | 3/3 |
| 进程退出 | 1，预期失败 | 0，77/77 |

40个负例=5键×8项：未知字符串、合成机密marker、空字符串、错误大小写、integer、boolean、array、map。每点同时注入prompt/body/user.id/subject/site/siteId/releaseId/traceId/requestId/authorization/db.statement，并在resource再次注入；原始查询和完整series索引均没有这些键和值。所有测试内容为明确合成数据。

RED config SHA256=0983213699a64af5f2dc8134ad7a45d34545ce7fade6dafdd1cdd82912b3ad83，原配置保存在[只读快照](config.before.alloy)。最终格式化config SHA256=ece43d2e118aa18138f2cfc66e8f06a1077f19dbf0983e5900668e7d76e4b6a7。中间未格式化GREEN与最终格式化GREEN均保留，结论以green-formatted为准。

## 其他验证与真实失败

- [仓库检查](repository-checks.json)：pwsh -NoProfile -File scripts/verify.ps1 -SelfTest exit0；工程检查器8项、结构化文件4项、环境3组、toolchain4个摘要正反例、ReviewPackage35项0失败；Doctor两个边界通过。内部“invalid.yml/TOML”输出是预期负例。Python AST和git diff --check均exit0。没有修改或弱化既有门禁。
- [官方格式检查](format-check-final.json) fmt --test exit0；每轮真实Alloy validate exit0。初次fmt --test exit1后只格式化owned配置，[原始失败](format-check.json)和[格式化命令](format-apply.json)保留。
- [夹具首次启动失败](setup-failure/result.json)：Docker --internal网络不发布回环端口，未发送OTLP；只清本人资源后改为独立普通网络、仍仅随机回环端口。最终所有目的地是本人新容器或容器回环不可用日志/trace出口，无外部请求。
- SelfTest首次重定向到仓库内正在写入的log造成自扫描失败，改为subprocess内存捕获、结束后写证据；[失败命令](setup-failure/self-test-inplace-command.json)与[失败输出](setup-failure/self-test-inplace.txt)保留。最初shell包装使用zsh只读变量status导致包装退出1；验证后续使用任务专属变量/标准库捕获，没有修改shell全局配置。
- 每个容器限256MiB、1CPU、128PID，Prometheus临时TSDB tmpfs96MiB、Alloy临时数据tmpfs32MiB，独立随机网络/名称/回环端口，无旧volume或runtime。finally只删本人新资源，所有真实轮次ownContainersRemaining=[]，网络删除exit0，未Docker prune。

## 限制与下一责任人

- NOT_RUN：本任务使用合成OTLP，四种产品形状也由夹具构造；没有以本机MeterListener或合成输入替代真实产品Meter E2E。Host AddSources/AddMeters、产品真实发射与全栈G1/G2 Loki/Tempo/Prometheus关联/series由Master负责。
- NOT_RUN：本任务没有运行.NET/Web编译或产品测试、真实模型/生产/Windows/Intel；配置与stdlib脚本变更使用实际collector链路验收，产品门禁由Master最终集成覆盖。
- NOT_VERIFIED：本任务分支CI没有查询运行，不推断空status；需要最终集成Head CI run ID/URL及结论。
- 独立Review待Master另派；Owner不派子Agent、不自任Reviewer。唯一标准审查ZIP由Master在最终提交与CI核验后构建并重开验证，本子任务不另出ZIP、不合并main。完成证据提交后停止，释放slot。

Master审查包预检：标准包禁止.log后缀，现将该次自测命令输出同字节移动为setup-failure/self-test-inplace.txt，未删除失败内容或改写原始命令。原历史路径/提交仍可追踪，映射及SHA见master/review-package-path-normalization.json。
