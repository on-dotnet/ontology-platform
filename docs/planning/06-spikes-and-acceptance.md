# 06 · PoC、验收与测试计划

以下脚本名称是 **批准后应实现的入口**，当前均不存在、均为 **NOT_RUN**。每次执行应保存环境、提交、资产版本、样本、命令、退出码、日志、Trace和判定。文档归档检查不等同下列PoC或产品测试通过。

## PoC清单

后续统一执行格式：`pwsh ./scripts/acceptance/<名称>.ps1`。

| 名称／Owner | 实验与样本 | 成功标准／失败退路 |
|---|---|---|
| `semantic-roundtrip`／Semantic | 复杂OWL、公理列表、空白节点、语言/类型字面量、imports；导入编辑导出、SHACL/SPARQL | 图同构及必要源码保留；不能编辑的内容明确只读或阻断 |
| `jena-recovery`／Semantic/SRE | 目标规模、备份、崩溃、恢复、版本图隔离 | 达到批准恢复目标且查询正确；否则限制拓扑并评估RDF4J |
| `source-matrix -Profile Local`／Connectors | 五源测试环境；PG/Oracle比较Ontop与原生；TDengine独立验证；Doris/API独立Adapter | 结果、授权、分页/超时正确；不兼容源走批准的原生Adapter |
| `release-faults`／Backend | 对上传、Jena部署、回验、CAS、Outbox逐点故障注入 | active不指向缺失制品、不混版、重试幂等；失败阻止G2验收 |
| `identity-mapping`／Connectors | 跨厂重号、别名、历史编码、缺失、多对多、单位时区 | 不静默误合并，歧义可处理；未决身份返回AMBIGUOUS |
| `metric-rule-determinism`／Metrics | 固定输入、版本、生效期、精度、零分母及缺失 | 结果可重复、证据完整；不足时规则返回无法判定 |
| `bff-security`／Security | Keycloak、SSR、双实例、Cookie、CSRF、登出、密钥共享、跨厂负例 | 无越权及凭证泄漏，会话行为一致；失败阻止G1 |
| `sse-proxy`／Backend/FE | .NET→YARP→Next/浏览器链路，断线、重放、慢客户端、取消 | 无静默丢事件，代理不缓冲，游标及取消可解释 |
| `run-recovery`／AI | MAF Checkpoint、PG Run、租约接管、重复工具、审批变更、模型切换 | 不跳过审批、不重复产生副作用；失败限制无人值守流程 |
| `knowledge-review`／Knowledge | 许可文档、扫描件、OCR、Chunk/Embedding、候选与恶意指令 | 页/片段证据可定位，接受只入草稿；保留人工工作流 |
| `observability-dr`／SRE | LoggerMessage→OTel/Alloy→LGTM、中文告警、独立审计、恢复 | Trace贯通、核心审计不丢、恢复清单一致 |
| `rustfs-compat`／SRE | 所需S3操作、大对象、权限、恢复；发布包、文档、Loki/Tempo各消费者 | 分别通过所需子集；不将一个消费者成功外推到全部 |
| `ui-workspaces`／Frontend | Base UI、SSR、水合、Cytoscape、Monaco、主题、键盘和大图 | 真实交互完整、无水合错误、关键流程可访问 |
| `toolchain-spikes`／Platform | Kiota/Hey API、MSTest/MTP、Hangfire/替代方案相同小样例 | 合同兼容、维护和许可可接受；候选失败用批准最小方案 |
| `rca-eval`／AI/Quality | Q235B正确谱系、反证、缺证据、部分源故障、注入和越权 | 可解释、引用正确、标明未知及替代假设，不把相关性当因果 |

外部生产凭证、专有标准、付费模型或真实工厂数据缺失时，采用标记为Local/Synthetic的测试集；不能据此完成真实环境验收。真实五源验收另用受批准、只读的隔离环境配置。

## 构建与验收入口

批准后建立以下入口；本轮未执行：

```text
pwsh ./scripts/doctor.ps1
pwsh ./scripts/dev.ps1
pwsh ./scripts/verify.ps1 -Profile CI
pwsh ./scripts/acceptance/g1-foundation.ps1
pwsh ./scripts/acceptance/g2-thin-slice.ps1
```

`verify`组合原生工具，分别报告结果：

```text
pnpm install --frozen-lockfile
pnpm turbo run lint typecheck test build
dotnet tool restore
dotnet restore backend/OntologyPlatform.slnx --locked-mode
dotnet build backend/OntologyPlatform.slnx -c Release --no-restore
dotnet test --solution backend/OntologyPlatform.slnx -c Release --no-build
dotnet format backend/OntologyPlatform.slnx --verify-no-changes --no-restore
pnpm --filter @ontology-platform/web exec playwright test
```

MTP命令形式由工具链PoC验证后固定。真实集成和E2E不使用结果缓存。Python Worker在引入阶段增加独立锁定、测试及安全检查，不伪装为npm包。工程尚不存在时不得以空目标或零测试执行宣称成功。

## 门禁

- 架构：Domain外部依赖、跨模块写入、ServiceDefaults污染、禁用依赖及命名检查。
- 合同：OpenAPI、生成客户端、SSE、MCP Schema、发布包及版本兼容。
- 安全：授权、CSRF、SSRF、连接器只读、工具预算、文档注入、证据脱敏。
- UI：关键闭环、加载/空/错/拒绝、中文、主题、键盘、SSR和取消重试。
- 性能：G1建立可重复基线，G2测端到端延迟，G4测跨源预算，G8按批准SLO压测。
- 恢复：激活故障、Run接管、备份完整性和隔离恢复。
- 发布：独立审查、依赖许可、SBOM、离线交付和未解决风险记录。
