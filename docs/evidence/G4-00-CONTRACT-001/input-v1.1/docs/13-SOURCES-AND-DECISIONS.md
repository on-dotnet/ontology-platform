# 13 · 来源登记、事实/提案标注和 ADR 裁决台账

本档记录 2026-11-01 本轮核对时可公开读取的官方资料。联网资料证明“厂商文档如此描述”，不证明本项目实际安装/连接/运行已经通过。阅读者须核对其适用版本；引用文字不作为自动升级授权。

## A. 仓库事实（通过连接的 GitHub 仓库直接读取）
| 文件 | 现有权威事实 | GitHub 路径 |
|---|---|---|
| main branch | `d1a61daffe844475b07705797e3ad325cc3f2945`，G6支线未合 | https://github.com/on-dotnet/ontology-platform/tree/d1a61daffe844475b07705797e3ad325cc3f2945 |
| 01-decisions-and-nongoals | RDF/OWL/SHACL/SKOS、.NET10、Next/shadcn、G3权威和非目标 | `docs/planning/01-decisions-and-nongoals.md` |
| 03-module-feature-matrix | 五源连接、实体图谱、Semantic Gateway、指标、Agent/G6模块依赖 | `docs/planning/03-module-feature-matrix.md` |
| 04-roadmap | G3→G4→G5→G7→G8关键路径，G6并行到G7 | `docs/planning/04-roadmap-and-dependency-dag.md` |
| G2 thin-slice frozen | ActorContext/ResourceScope/CommandContext/SourceBundle、Gateway六态、MCP白名单/预算、发布原子性 | `docs/contracts/g2-thin-slice-contracts.md` |
| G3-M4-contract-a | IdentityClaim、源命名空间、半开有效区间和未知时间语义 | `docs/contracts/g3-m4-contract-a.md` |
| G3-M4-contract-b | 任两版本Diff、影响范围、异人审批时绑定影响hash | `docs/contracts/g3-m4-contract-b.md` |
| G3-M5 | 高阶OWL只读投影、现行策略/历史版本分离 | `docs/contracts/g3-m5-contracts.md` |
| local-validation-policy | 本地真实验收优先，GitHub Actions按需手动，未运行保留NOT_RUN | `docs/development/local-validation-policy.md` |
| review-package-spec | 唯一V3、输入绑定、真实独立重开 | `docs/development/review-package-spec.md` |
| resource-lifecycle | Worktree/Docker/历史证据归属，DryRun后精准清理 | `docs/development/resource-lifecycle.md` |

## B. 官方连接器和安全资料
| 主题 | 官方资料 | 设计应用 |
|---|---|---|
| PostgreSQL metadata | https://www.postgresql.org/docs/current/infoschema-columns.html | 可见列只对当前用户权限，不能把空结果视为全库无列 |
| PG read only | https://www.postgresql.org/docs/current/sql-set-transaction.html | 事务READ ONLY只是防线之一 |
| Oracle ODP.NET | https://docs.oracle.com/en/database/oracle/oracle-database/26/odpnt/InstallODPCore.html | .NET Core Provider和非Windows NuGet部署；商业与架构另核 |
| Oracle Schema | https://docs.oracle.com/en/database/oracle/oracle-database/26/odpnt/featConnecting.html | `GetSchema()` 提供 metadata集合，实际权限/Edition需验证 |
| Oracle DDL metadata | https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_METADATA.html | `DBMS_METADATA`有特权模型，不建议默认提升源权限 |
| Doris MySQL wire | https://doris.apache.org/docs/4.x/db-connect/database-connect/ | FE默认查询端口9030，客户端可用MySQL协议 |
| Doris兼容限制 | https://doris.apache.org/docs/4.x/query-data/mysql-compatibility/ | MySQL协议兼容不等于类型/SQL行为完全相同 |
| TDengine C# | https://docs.taosdata.com/developer-guide/connectors-reference/csharp/ | WS跨平台，C# native退场通知2027-01-01 |
| TDengine WS迁移 | https://docs.taosdata.com/developer-guide/connect/ | 迁移由Native到WebSocket与taosAdapter交互方式 |
| TDengine REST | https://docs.taosdata.com/developer-guide/connectors-reference/rest-api/ | POST body执行SQL是厂商特例，G4需单独限制 |
| OWASP SSRF | https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html | DNS/IP验证、防重绑定、代理/redirect/重试与目的地许可 |
| .NET HttpClient | https://learn.microsoft.com/en-us/aspnet/core/fundamentals/http-requests?view=aspnetcore-10.0 | 统一配置、timeout、handler lifetime；新增依赖按审批 |
| Docker project isolation | https://docs.docker.com/compose/how-tos/project-name/ | Compose ProjectName精确隔离任务资源 |
| Ontop VKG | https://ontop-vkg.org/guide/ | R2RML虚拟关系型知识图，PG/Oracle可对照，不默认替换五源 |
| MySqlConnector | https://github.com/mysql-net/MySqlConnector | MIT商业使用的MySQL wire .NET候选，仍需 Doris实测 |

## C. Codex 官方近期实践（用于每次任务前核对）
- 2026-09-11 Rethinking skills and prompts for GPT-6 Astra：https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra。要点：精简AGENTS/skills，按需加载，不层层叠加同一限制。
- 2026-08-03 Iterating Development Workflows with Codex：https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex。要点：小任务、分阶段证据和批准边界，规划与实施分别授权。
- 2026-05-09 Using Goals in Codex：https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex。要点：Outcome/Verification/Constraints/Boundaries/Iteration/Blocked Stop。
- Codex ExecPlans：https://developers.openai.com/cookbook/articles/codex_exec_plans。要点：完成条件可观察、计划可独立执行、回退清晰。
- OpenAI 模型推理强度：https://developers.openai.com/api/docs/guides/reasoning。要点：High适合复杂规划，Medium适合一般可验证任务；具体模型以当前 Codex客户端可选项为准。

## D. G4 ADR 初始裁决与批准级别
| ADR | 建议设计 | 此次状态 | 实测决定因素 |
|---|---|---|---|
| G4-ADR-01 | G4元数据独立PG schema、SecretRef脱敏 | PROPOSED | 真实密钥/治理审计/兼容 |
| G4-ADR-02 | 五源共用受控typed query SPI，保留方言独立 | PROPOSED | 真实驱动/类型/只读负例 |
| G4-ADR-03 | WebAPI先GET+明确Operation白名单，HTTP/网络安全 | PROPOSED | SSRF/redirect/proxy/内网审批回归 |
| G4-ADR-04 | Ontop只对PG/Oracle做比较，不强制全平台 | PROPOSED | 精确对照、权限/版本、运维开销 |
| G4-ADR-05 | MappingRelease独立G3 OntologyRelease、异人审批+CAS | PROPOSED | 发布故障/审计原子性和G3读兼容 |
| G4-ADR-06 | 六态与独立SourceReadReceipt/水位/时态 | PROPOSED | 五源分页/不同时态/部分失败 |
| G4-ADR-07 | G4权限action加入Governance白名单及Secret策略 | PROPOSED | Keycloak/G2 Guard/权限反例 |
| G4-ADR-08 | Compose Linux arm64/amd64阶段真测，任务资源清理 | PROPOSED | 容器/驱动/许可证与Mac/Windows实机 |

## E. 授权留白
本次没有批准 `G4-00-CONTRACT-001` 的 Codex仓库执行，没有批准 G4-M1、Oracle driver/商用许可购买、部署镜像、Docker新容器、生产数据源、外部模型/Token、main合并。只有进一步明确人类批准才可推进。尚未运行的部分不得为了“满足验收表”生成伪证据。

## V1.1 直接源码对照（2026-11-01）

- GitHub `on-dotnet/ontology-platform` 主线 G3 Head：`d1a61daffe844475b07705797e3ad325cc3f2945`。
- `backend/src/Contracts/OntologyPlatform.Contracts/G2Models.g.cs`：`SemanticQueryResult` 11字段、`EntityCandidate` 7字段、`EvidenceRef` 正式图来源与 Scope 字段、`AssetVersionSnapshot` 不可变图/Hash、`SemanticSubSource` 状态/版本、`CommandContext.expectedRevision` 创建0。
- `backend/src/Hosts/OntologyPlatform.Api/G2/SemanticEndpoints.cs`：现有 `POST /api/v1/semantic/queries`；G4新提议路径是 `POST /api/v1/data/semantic-queries`，互不替代。
- 本次 V1.1 合同来源包含用户审查的 P1/P2 四项问题。厂商外部规格和实际 .NET/OpenAPI 运行仍需后续授权独立验证。
