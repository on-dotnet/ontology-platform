# G2-THIN-SLICE-001 执行计划与恢复账本

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development。用户已明确独立Worktree/多Agent并行执行，无需重复确认执行方式。此卡按PLANS.md兼实施计划，契约审查前不得派发产品写任务。

**Goal:** 从可信Synthetic OWL/Turtle草稿经真实SHACL/异人审核/不可变发布，完成受控REST/MCP查询、持久Run/SSE/证据及回滚。
**Architecture:** 保持模块化单体、独立Domain/模块DbContext与所有权；Jena正式语义、PG权威激活/CAS/审计/Outbox、RustFS不可变对象，原G1安全与遥测复用。
**Tech Stack:** 已锁.NET10/EF10/Next16/React19/Base UI/Tailwind与Jena6.2.0；新精确依赖先登记验证，不浮动升级。
**Spec:** [人类明确批准的授权V1](../evidence/G2-THIN-SLICE-001/authorization-v1.md)。
**BaseSha:** `6154ebb3703031a49cf0c555c9f0c3596e3b7726`。

## Global Constraints

仅G2，禁止G3–G8自动推进、生产/付费模型/管理员/全局配置。main唯一集成人Master；独立写Agent独立托管Worktree/分支，其他人在工作，不回退覆盖。共享契约/迁移/锁/CI/AppHost/Design Tokens单写者。所有手写C#成员准确中文XML、局部变量中文用途注释；TS复杂逻辑中文JSDoc。无原始正文/异常/密钥进遥测。不用Mock或静态配置冒充业务成功。历史PARTIAL保留；模型未获准可用则真实模型BLOCKED，确定性工具链单独验收。

## Review Focus

1. 未支持公理/import/空白节点编辑必须保留或阻断，禁止源码转画布时丢失。
2. 草稿修订/审批有效期/主体分离与发布并发须在最终激活前复核，不靠UI。
3. 外部图/对象已就绪再同PG事务CAS+Governance审计+Outbox，响应丢失按事实恢复。
4. 跨厂同号歧义、证据二次授权、固定版本与源失败不能被EMPTY/字符串Join掩盖。
5. 事件先存后发、游标/慢客户端/取消/租约恢复，SSE无权改变审批状态。

## 任务DAG与门禁

- [x] 0. 完读授权/根规则/现状，fetch并确认Base，保留六个用户.DS_Store和全部历史树。
- [ ] 1. 只读调查、兼容依赖/许可登记，Master冻结共享契约/ADR/DTO/任务所有权，独立契约审查。
- [ ] 2. S1：SEM真实解析/SHACL/标准样例与FE真实草稿工作区并行；Master共享迁移/Host/生成合同；独立Review后增量main。
- [ ] 3. S2：PUB审批/不可变对象/隔离图/回验/CAS/Outbox/调和及故障回滚，FE集成；独立Review后增量main。
- [ ] 4. S3：QRY正式能力/六态/证据后AI真实MCP/MAF受控Provider/持久Run与SSE，FE接入；独立Review后增量main。
- [ ] 5. QA：十类真实入口/G1回归/真实LGTM/浏览器全链/性能样本、独立整体Review及修复。
- [ ] 6. 最终同Head CI/主线push/文档与真实状态、唯一标准ZIP构包并独立重开，交付后停止。

## 初始所有权

Master：`codex/G2-THIN-SLICE-001-master`，`/Users/chasen/.codex/worktrees/g2-master/ontology-platform`。公共合同/目录项目注册/中央包与全部锁/迁移/CI/AppHost/Design Tokens/授权和总证据唯一Owner。SEM/FE已建立独立树`/Users/chasen/.codex/worktrees/g2-sem/ontology-platform`/`codex/G2-SEM-001`与`/Users/chasen/.codex/worktrees/g2-fe/ontology-platform`/`codex/G2-FE-001`；owned_paths见下具体任务。PUB/QRY/AI在前置门通过后分别创建同名g2-pub/g2-qry/g2-ai托管树及codex/G2-PUB-001、codex/G2-QRY-001、codex/G2-AI-001分支，实际创建回执再登记，不虚称已存在。每项Reviewer由Master另派独立quality_reviewer（实现者无审查自身写入权）；首个契约Reviewer=g2_contract_review。未冻结前仅调查/批准的隔离兼容PoC，无产品写任务。

## 恢复账本

2026-10-26：已完整读取授权，基线及fetch远端同6154ebb；Master新托管树并建任务分支。g2_semantic_design/g2_runtime_design/g2_frontend_design仅只读调查，无产品写任务。根.agents目录不存在；实际角色位于.codex/agents。G1审查包/私有runtime/卷全部保留且不复用认证材料。当前共享合同尚未冻结，所有G2真实运行验收NOT_RUN。优先核实Jena官方内置SHACL operation以避免新Java服务架构。

## 具体实施任务（唯一共享合同以独立审查通过版本为准）

### Task 1: Master合同、运行组合与共享基础

**Files:** `docs/contracts/g2-thin-slice-contracts.md`、ADR-009、唯一`backend/src/Contracts/OntologyPlatform.Contracts/**`；所有项目/solution/CPM/lock/迁移；`Modules/Governance/OntologyPlatform.Modules.Governance/TransactionalAuditWriter.cs`及其专属合同；`Api/G2/G2Authorization.cs`、`G2EndpointGuard.cs`、宿主原文件；AppHost/Fuseki配置；TS生成器/client及Design Tokens。
**Interfaces:** 具体化合同§3–7的唯一DTO与显式用例接口，全部Owner消费同一项目。Master持有运行开关与安全组合，无G2配置的历史G1测试保持原路由能力；启用G2时严格配置与真实探针，不悄悄fallback。所有新依赖仅批准精确包和安全闭包。

- [ ] 1. 对完整合同/Task DAG/Single Writer进行独立固定提交审查，P0/P1关闭才冻结。
- [ ] 2. 先为enum/union/null/字典生成和授权/CSRF/事务Enlist写有意义负例并确认失败，再实现唯一DTO/原生Auth/生成器，不写镜像式测试。
- [ ] 3. 受控恢复精确依赖，登记传递许可/audit与兼容。还原原锁时保留失败原因，不重写历史证据。
- [ ] 4. Master生成各模块真实EF迁移，运行全新PG/升级与有数据Down保护，注册真实AppHost资源及新独立开发身份。
- [ ] 5. `verify.ps1 -SelfTest`、受锁Release/format/SDK与客户端语义校验通过后commit/push；产品链分阶段独立Review后集成main。

### Task 2: G2-SEM-001 — S1语义与持久草稿

**Files:** owned `backend/src/Modules/Ontology/OntologyPlatform.Modules.Ontology.Domain/**/*.cs`、`.../OntologyPlatform.Modules.Ontology/**/*.cs`（排除Migrations）、`backend/src/Hosts/OntologyPlatform.Api/G2/OntologyEndpoints.cs`、`backend/tests/OntologyPlatform.SemanticTests/**/*.cs`、`samples/g2/**`、`scripts/acceptance/semantic-roundtrip.py`、`shacl-validate.py`、`draft-revision.py`、`docs/evidence/G2-THIN-SLICE-001/SEM/**`。全部csproj/锁/迁移/公用DTO/配置只读，新增文件名先在任务卡锁定。
**Interfaces:** 消费唯一合同ActorContext/CommandContext/SourceBundle/Hashes/Projection/Validation/Draft；产出`OntologyService`草稿create/read/list/save/edit/diff/validate与`JenaSemanticRuntime`内部RDF/SHACL适配；向PUB公开scope/revision/hash校验及共享连接事务内只读锁定用例，不让PUB直写ontology表。注入`TimeProvider/IHttpClientFactory`、纯Domain无EF/HTTP。接口签名以Master唯一Contracts为准。

- [ ] 1. 先在真实Jena和PG写红例：中文/语言/类型/空白节点/未知公理/import/no-op字节；五类合法/缺业务键/非法datatype/class/range/关系的标准SHACL报告；旧revision409、scope403、修改审批失效依PUB状态交叉测试。
- [ ] 2. 实现RIOT受控解析与完整源持久历史、显式支持清单/阻断；结构编辑只动被准许精确三元组，未知结构不能被投影覆盖。非法源码保留客户端，不写坏修订；暂存finally清理，非法Shape/SPARQL/import阻断。
- [ ] 3. 写真正Synthetic五类、多对多/缺关系/双厂同号/来源完整的Turtle与Shapes，通用runtime不硬编码行业类。
- [ ] 4. 按合同实现CAS草稿和与Governance-owned审计的原子事务；提供明确模型给Master生成迁移。真实脚本输出命令/退出码/测试数/hash/失败与绿证据，全部中文C#注释。
- [ ] 5. 用真实MSTest/MTP/Jena脚本证明S1，受锁构建/format/SelfTest后提交push分支，独立Review完整Base..Head；不得自行main。

### Task 3: G2-FE-001 — 真实编辑、审核与查询运行工作区

**Files:** owned `apps/web/src/features/{ontology,publishing,semantic,agent}/**`、`apps/web/src/features/platform/workspace.tsx`、新`apps/web/src/app/ontologies/**`、`apps/web/src/app/releases/**`、`apps/web/src/app/analysis/**`、`apps/web/src/components/ui/semantic-*.tsx`、`apps/web/tests/g2/**`、`docs/evidence/G2-THIN-SLICE-001/FE/**`。共享types/client/生成器/Tokens/包锁只读。模块样式新`apps/web/src/features/ontology/workspace.css`沿用tokens，不能改全局tokens。既有G1测试不要改断言获得绿。
**Interfaces:** 只消费Master生成OpenAPI types和client协议，结构编辑经Ontology真实命令，不浏览器解析重建OWL。与SEM并行，未有实际接口的UI只可标待联调，不能作为E2E通过。S2/S3滚动接PUB/QRY/AI真实服务。

- [ ] 1. 先阅读真实安装版本Next dist/docs，先写有意义dirty/409保留文本/加载拒绝/跨chunk SSE/去重与取消测试；记录红例。
- [ ] 2. Monaco/Cytoscape自有Client懒加载adapter、本地worker与SSR边界；三栏/390tabs，同revision源码/图/表单/SHACL/Diff真实联动，未知公理只读/阻断明确。图布局不推进revision；移动用真实textarea fallback。
- [ ] 3. 审核页显示精确hash/revision/主体/范围/过期，真实异人批准/拒绝；发布/回滚真实manifest/状态/Trace，按钮均有真实结果；没有权限不靠UI作为安全。
- [ ] 4. 六态查询/证据再次读取、模型未配置和确定性harness标记、Run持久事件/Last-Event-ID/终态/取消、诊断入口；XSS文本渲染，卸载仅断开订阅。
- [ ] 5. 精确锁lint/typecheck/Vitest/build及真实浏览器1440/1280/390主题/ARIA/键盘/worker/水合/全链测试。截图安全不含认证材料，无真实API部分NOT_RUN；分S1/S2/S3持续commit/push/review。

### Task 4: G2-PUB-001 — S2安全发布与回滚

**Files:** owned `backend/src/Modules/Publishing/OntologyPlatform.Modules.Publishing.Domain/**/*.cs`、`.../OntologyPlatform.Modules.Publishing/**/*.cs`（排除Migrations）、`Api/G2/PublishingEndpoints.cs`、`backend/tests/OntologyPlatform.PublishingTests/**/*.cs`、`scripts/acceptance/release-faults.py`、`docs/evidence/G2-THIN-SLICE-001/PUB/**`。共享合同/迁移/项目/锁/Host只读。
**Interfaces:** 消费Ontology固定revision/验证/受控runtime、Governance-owned enlisted审计、唯一Manifest/Snapshot/Proposal；产出`PublishingService`提案/异人审批/准备/激活/回滚/manifest读取与`PublishingDbContext`、`ReleaseOutboxDispatcher`。Master注册DI/迁移。正式graph和不可变object供QRY固定snapshot读取。

- [ ] 1. S1最小验证通过后先真实负例：无批准/自批/角色/过期/修改revision；RustFS/Jena写及回验/PG/CAS/审计/Outbox逐点故障、响应丢失、并发发布/ABA与幂等payload冲突；草稿已推进到revision2后ROLLBACK到R1正例，以及篡改目标manifest/过期/自批负例。
- [ ] 2. .NET内置受控S3 SigV4适配精确所需子集，不新增AWS包；不可变源/manifest GET hash回验；隔离版本图/真实SHACL及正式查询一致后才能短事务激活。
- [ ] 3. 用同物理PG连接/txn、模块owned writer和固定锁顺序原子CAS+audit+Outbox，失败旧active保持；dispatch至少一次/去重/fencing及调和真正执行，不只建空表。
- [ ] 4. 异人审核的旧完整版本回滚、历史图保留、Run旧snapshot不混版，缺制品UNAVAILABLE；记录真实故障/恢复/幂等证据。
- [ ] 5. MSTest真实PG/S3/Jena/SelfTest/format及脚本通过后提交push，独立固定差异审查后Master S2增量集成main。

### Task 5: G2-QRY-001 — 正式语义Gateway与证据

**Files:** owned `backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/**/*.cs`、`Api/G2/SemanticEndpoints.cs`、`backend/tests/OntologyPlatform.QueryTests/**/*.cs`、`scripts/acceptance/query-plan.py`、`docs/evidence/G2-THIN-SLICE-001/QRY/**`。合同/项目/锁/迁移/其他模块只读。
**Interfaces:** 仅从Publishing读取获授权真实manifest/snapshot，Jena正式版本graph读取标准三元组；唯一`SemanticGateway.ExecuteAsync(ActorContext,SemanticQueryPlan,CancellationToken)`、`EvidenceService`供REST/MCP/Agent。Capability Registry固定三能力，SchemaCatalog从正式ontology派生，不硬编码五类答案。

- [ ] 1. 先真实测试FOUND/EMPTY/PARTIAL/UNAVAILABLE/UNAUTHORIZED/AMBIGUOUS，双厂同号、多对多、限额/未知路径/图丢失/错hash、跨厂Evidence二次拒绝。
- [ ] 2. 实现深度/行数/时间/关系/身份scope约束，只有固定受控操作，避免字符串注入或生产任意SPARQL；本体版本与事实有效/观察时间分开。
- [ ] 3. 从真实assertion provenance构造Evidence，缺源不造事实；读取时再次授权和hash，正式图不可用不返回EMPTY；PG独立审计、有限诊断/Trace。
- [ ] 4. 真实Query脚本/PG/Jena/MSTest/format/SelfTest通过，提交push并独立Review，提供AI同一Gateway而非复制查询。

### Task 6: G2-AI-001 — 真实MCP/MAF与持久SSE

**Files:** owned `backend/src/Modules/Agents/OntologyPlatform.Modules.Agents/**/*.cs`（排除Migrations）、`Api/G2/ExecutionEndpoints.cs`、`Api/G2/McpEndpoints.cs`、`backend/tests/OntologyPlatform.AgentTests/**/*.cs`、`scripts/acceptance/mcp-agent.py`、`sse-replay.py`、`docs/evidence/G2-THIN-SLICE-001/AI/**`。共享DTO/锁/项目/迁移/Host只读。
**Interfaces:** 复用唯一Gateway/Capability/Evidence/Authorization，唯一`ExecutionRunService`/PG`AgentsDbContext`及带fencing worker；MCP只明确三工具/服务器注入身份。真实模型默认禁用，安全deterministic harness必须通过真实MAF调用Gateway，不预写成功答案；未批准额外MAF直接包不能加。

- [ ] 1. 先真实SDK restore/compile PoC及MCP initialize/list/call；越权/注入/预算、无Provider状态；不把传递AppHost MCP当产品实现。
- [ ] 2. 真实PG Run/snapshot/事件，先存后发/seq唯一/终态/租约接管fencing/取消；同事务Governance审计；Tools只读，不把MAF checkpoint说成已证跨模块ACID。
- [ ] 3. .NET原生SSE/PG重放/Last-Event-ID，跨run/未来游标拒绝，慢客户端/25秒换连、注销重授权、断流与取消分离，YARP代理和浏览器实际延迟验证。
- [ ] 4. 真正调用MAF的本地安全harness+实际Gateway/正式图工具回答/证据，不靠预写字符串；真实模型明确BLOCKED，不调用收费/云模型。
- [ ] 5. mcp-agent/sse-replay真实脚本/MSTest/format/SelfTest通过后commit/push独立Review，Master S3集成。

### Task 7: G2-QA-001 — 独立整体与全链验收

**Files:** Master owned `scripts/acceptance/full-g2-e2e.py`、`g1-regression.py`、`performance-baseline.py`、`g2-thin-slice.ps1`、总证据/手册/交接/CI；Reviewer无写路径。
**Interfaces:** 固定最终Commit+完整Base..Head diff、十类实际脚本/运行时、已提交证据与唯一ZIP。Reviewer不得修改/弱化测试，发现问题回Owner复现/修复/限定复验。

- [ ] 1. 真正浏览器OIDC→草稿/结构编辑/验证/异人审核/发布→REST/MCP/MAF/持久SSE/证据→回滚/重查及新旧Run快照；必要负例与G1原安全/审计/LGTM回归。
- [ ] 2. 实际API/Jena SHACL/SPARQL/发布/SSE样本耗时分布/输入规模/环境，记录无生产SLO，模型/Windows/Intel/生产专项真实NOT_RUN/BLOCKED。
- [ ] 3. 独立语义/授权/发布一致性/工具安全/总体Review，重要缺口关闭后受锁构建/测试/同Head Linux CI。原CI和门禁不减。
- [ ] 4. Master唯一集成main并push，实际确认远端SHA及同Head CI；报告命令/退出码/未完原因/分支树/精确SHA。
- [ ] 5. 标准构包脚本生成唯一Review ZIP，独立VerifyOnly/逐成员散列/固定Git源/diff安全路径检查，交付绝对路径/size/SHA256和G2_THIN_SLICE_READY_FOR_REVIEW后停止。


2026-10-26 契约初审：de5f09f授权范围符合，0Critical/2Important/2Minor；未派产品写任务。已核实并修正回滚与当前草稿修订冲突（PUBLISH/ROLLBACK分支），补齐跨模块投影/查询/SSE载荷精确类型，明确Master治理事务writer路径和assetId永久唯一scope。兼容PoC实际恢复/编译/加载MAF1.26.0、AI10.11.0与MCP2.3.0，NuGet全传递已知漏洞查询未报告命中；完整许可登记与实际工具调用仍待验收。修正提交后限定复审，冻结后再派写。


2026-10-26实施增量：公共基础bd52431独立Review0Critical/4Important/1Minor：数据联合/事件封套与终态/null边界/空测试CI缺口及生成器测试发现路径。真实补例先7项中4失败，空工程实际exit8；修正G2专属序列化回调和标准Schema后19/19、生成器纳入Vitest9/9、typecheck/lint通过。移除四个空测试工程，真正测试源码到位才由Master恢复注册，不弱化既有门禁。原G1JSON全局行为不改变。公共输出Bootstrap仍schema-only不称真实端点验收。

用户明确继续暂停Monaco；未应用安全override，移除漏洞传递图，Cytoscape和其余工作继续。FE可实现原生备用能力但Monaco独立BLOCKED/PAUSED_BY_USER，不换第三方编辑器或冒充通过。

Master将手写Governance TransactionalAuditWriter.cs、API/G2/{G2Authorization,G2EndpointGuard}.cs及新G2SecurityTests/G2AuditTransactionTests临时明确转给唯一Owner g2_security_support；独立树/分支/精确路径见G2-SEC-SUPPORT卡。Master不同时写这些文件；唯一Contracts/项目/锁/迁移/Host/CI仍Master。

SEM模型fffb1af经独立0Critical/0Important/1格式Minor审查，已在Master以fcd7190 DRAFT集成，仅供真实迁移与后续S1测试，不main。Master局部EF10.0.13已成功生成InitialOntology迁移，未应用PG。SEM服务端新assetId必须服务端生成，clone通过唯一IReleaseCatalog.ReadAsync按releaseId重新授权取权威asset/scope；Save/Edit不能改变scope。正式graph规则冻结releaseId=GuidN，urn:ontology-platform:release:{releaseId}:ontology及:data。语义元数据命名空间urn:ontology-platform:vocabulary:，标准RDF reification/PROV-O带sourceId/sourceRecordId/validFromUtc/observedAtUtc/modelVersion/mappingStatus=absent；模型适用性还需正式manifest精确hash绑定，不能将合成模板版本冒充发布版本。


FE transport所有权调整：Master明确将全新lib/api/g2-client.ts及其测试单写权交FE；原G1 client/生成types/生成器/Tokens不交叉写。业务DTO/安全合同不变；这是独立文件所有权调整，不是新架构/依赖。当前FE写起点在Master同期已提交树（派发消息记录精确SHA），此前bd52431为共同合同基线。SEC40/40及限定独立0/0/0已经在29bff98集成任务树，尚未注册产品Host/主线。
