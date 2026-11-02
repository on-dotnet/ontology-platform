# 阻断交接与精确追加授权申请

状态：`BLOCKED_WITH_WITNESS`；这不是阶段 B 完成交付，也不是 main 合并审批请求。

P0 的当前远端、47 提交链、VR-11 历史交付、镜像内容映射和本地工具限定准入已核验。B 已建立专用工作树、私有依赖副本、宿主观察适配与四项边界测试；其余复制适配为 DRAFT，未准许运行。

廉价工程检查：锁定离线 restore/build exit 0；完整 format verify exit 2，275 项错误覆盖15文件（另2项IDE0161警告）。单API文件短复现仍exit 2。初步构建先于两处fixture白名单修改，不算稳定I01。两位非作者核实错误继承自候选源，未授权范围无法修复。

## 精确申请

请仅追加以下15文件的空白格式修复，以及正式Connections迁移文件的UTF-8 BOM移除。可审阅补丁是 [精确补丁归档](proposed-format-only.payload.json)，仅生成于ignored隔离副本；产品源码未应用。每个原始/建议散列见 [补丁输入绑定](proposed-format-only.json)。不改行为、SQL、迁移ID、namespace、规则、锁或依赖；仅警告的旧迁移不在申请内。获批后需独立Review、新TestedCommit和适用完整验收，不能直接沿用初步结果。

```text
backend/src/Contracts/OntologyPlatform.Contracts/ImpactContractRules.cs
backend/src/Hosts/OntologyPlatform.Api/G4/G4Endpoints.cs
backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/PgSourceAdapter.cs
backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.Catalog.cs
backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.Commands.cs
backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.cs
backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.Enable.cs
backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.Probes.cs
backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.Worker.cs
backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/ConnectionSecretCipher.cs
backend/tests/OntologyPlatform.AgentTests/AgentFixture.cs
backend/tests/OntologyPlatform.ConnectionsTests/PgFixtureSecurityTests.cs
backend/tests/OntologyPlatform.G2ContractTests/G3M4ImpactContractTests.cs
backend/tests/OntologyPlatform.QueryTests/QueryFixture.cs
backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Migrations/20261101115947_InitialConnections.cs
```

## 未完成项

| Gate | 状态与范围 |
|---|---|
| I01 | BLOCKED：初步格式见证失败；稳定T的27套工程SelfTest与4项宿主测试通过，完整native/Web门禁未完成 |
| I02–I07 | NOT_RUN：未启动任何任务容器、源库或浏览器 |
| I08 | PARTIAL：阻断见证/Review/唯一V3/资源收尾；不是全门禁闭合 |

尚缺 run.py、consumer_check.py、runtime.py、module-tests.py、startup-boundary.py、migration-boundary.py、contract-check.mjs、readback.py、closeout.py、hooks/pre-push。已有fault.mjs仍带历史RunId/固定日期，g3-compatibility.mjs仍带与新Compose不同的容器名；全部保留DRAFT且未执行。不能绕开consumer准入直接调用。

CI/Windows/Intel：NOT_RUN；当前在线签名、CVE、完整许可证：NOT_VERIFIED。历史49项保持INHERITED_NOT_RERUN。AMBER-A1只限内部合成非分发。阶段C/main、M2/G6未执行且未授权。

资源收尾记录在本任务resource-closeout证据；工作树、任务分支、原始日志、审查ZIP与审批恢复材料保留，解除条件为后续明确修复/集成和生命周期批准。旧树、旧ZIP、主树六个DS_Store及共享缓存保持原样。

后续顺序：获批精确格式修复 → 先短复验 → 完成专用消费者/正反Review → 冻结新T → I01–I08完整验收 → 独立交付 → 另行main审批。

稳定部分验证提交：`e84b32e8b5e9c3eaefd32abe7b5f5e4c5e5ddaae`。已普通推送任务分支。实际回收48个精确可再生目录，逻辑字节2,697,464,462；不宣称物理释放同等空间。4391跟踪文件散列保持，1283链接未跟随，主树六个DS_Store不变；任务容器/卷/网络创建0，宿主监测进程退出0并确认PID缺席。见 [实际资源回执](resource-closeout.json) 与 [本地验证](validation.json)。

首次构包因补丁展开的一行C#属性成员引用命中有限秘密规则而拒绝（exit 1），未生成ZIP。非作者确认不是凭证字面量且同表达式在S/T已存在；未改扫描器。现以base64/SHA/字节数归档完整原补丁，ignored保留可读副本，最终重开须独立解码核验。原始失败见 [构包诊断](package-first-attempt.json)。
