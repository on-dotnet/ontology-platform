# 05 · Agent团队与任务合同

本文件为 **PROPOSED** 研发组织和任务合同；不授予执行权限。审批事实见 [10](10-g0-review-record.md)。

## 岗位与写入边界

| 岗位 | 主要所有权 |
|---|---|
| Master/Integrator | 审批映射、ADR、公共契约冻结、集成及总验收 |
| Domain/Semantic | `semantic/`、Ontology/Validation/Publishing模块 |
| Backend Platform | API/BFF、安全、BuildingBlocks及模块设施 |
| Connectors/Query | Connections、Identity、EntityGraph、SemanticQuery |
| Metrics/Rules | 指标规则定义、计算及版本 |
| Knowledge/AI | Worker、Knowledge、Agents、MCP、SSE和Evals |
| Frontend/Design | `apps/web/`；Design Tokens指定单一作者 |
| Quality/Security | 独立审查、架构/契约/安全/端到端验收 |
| SRE | `infra/`、观测、部署、备份恢复及离线交付 |

G0观察到可用并发为主会话加三个子Agent。实施默认最多三个编辑任务并行，并为审查释放槽位；不将逻辑岗位数量等同并发数量。

子Agent共享当前目录，不天然隔离。每个写任务必须明确进入独立managed worktree/分支；根集成目录不接受并发改写。分支默认`codex/<task-id>`。

任务交接记录保存到`docs/tasks/`，证据到`docs/evidence/`。消息用于协调，持久事实以任务卡、提交、PR和证据为准。

## 起始任务DAG

以下任务均为`proposed / awaiting_authorization`。G0归档批准不启动任何一项。

| 任务 | 依赖 | 产出 |
|---|---|---|
| G1-ENG-001（首个） | G0归档、专用G1授权、相关ADR决定 | 命名、根配置、工具锁定、CI基础、AGENTS提案落地 |
| G1-INFRA-001 | ENG | AppHost、PG/Jena/RustFS/Keycloak开发资源、ServiceDefaults |
| G1-SEC-001 | INFRA | BFF登录、资源授权、CSRF、多实例会话、审计 |
| G1-FE-001 | ENG、认证合同 | Shell、主题、中文状态、真实登录资源页 |
| G1-OBS-001 | INFRA、审计合同 | LGTM关联、中文入口和告警基础 |
| G2-SEM-001 | G1验收 | 最小OWL/SHACL与真实Jena查询 |
| G2-PUB-001 | SEM、发布合同 | 不可变制品、审核、激活、回滚、故障恢复 |
| G2-AI-001 | PUB、Run/Capability合同 | MCP、最小Agent、持久SSE、证据 |
| G2-E2E-001 | 上述任务 | 独立闭环验收及集成报告 |

## G1-ENG-001 首个执行任务计划入口

**状态：PROPOSED / awaiting_authorization。当前不得执行。**

**目标：**在批准的工程布局和Design System边界下，建立可追溯、可重复的最小工程规范与工具链基线；不实现业务功能，不启动基础设施和数据库迁移。

**Owner：**Backend Platform / Engineering，Master指定唯一作者。**Reviewer：**独立Quality/Security Reviewer，Frontend/Design复核Design System相关决定。

### 依赖

1. 本G0文档基线归档完成，读取[01](01-decisions-and-nongoals.md)、[08](08-agents-and-repo-standards-proposal.md)及[10](10-g0-review-record.md)。
2. 收到专用G1实施授权，明确是否只授权本任务以及安装/工具链验证范围。
3. ADR-001明确`packages/ui`暂缓提取方案与既有Design System决策的关系；不得默认为已批准。ADR-003/005中影响本任务的工具选型及新增依赖也须有明确决定。
4. 再次检查工作树、工具和当前安全补丁；本机观察不是长期锁版授权。

### 文件所有权（拟议白名单）

- 根工程配置：`global.json`、`Directory.Build.props`、必要时`Directory.Build.targets`、`Directory.Packages.props`、`NuGet.Config`、`.config/dotnet-tools.json`。
- 根前端工作区：`package.json`、`pnpm-workspace.yaml`、`pnpm-lock.yaml`、`turbo.json`、`.node-version`。
- 规则及说明：`AGENTS.md`、`PLANS.md`、`README.md`、`.editorconfig`、`.gitattributes`、`.gitignore`、`.dockerignore`、`.env.example`；适用的`backend/AGENTS.md`和`apps/web/AGENTS.md`。
- 研发配置：`.agents/skills/verify-change/**`（仅已有可运行验证入口时）、`.codex/config.toml`、`.codex/agents/**`；不得写用户全局配置或凭证。
- CI和验证：`.github/workflows/ci.yml`、`.github/CODEOWNERS`、Issue/PR模板，`scripts/doctor.ps1`、`scripts/verify.ps1`。
- 任务文档：本任务对应的`docs/tasks/G1-ENG-001.md`、`docs/evidence/G1-ENG-001/**`、相关ADR正文与依赖登记。
- 最小非业务工程入口：`backend/OntologyPlatform.slnx`及`apps/web/package.json`；如验证需要新增宿主、业务源码或额外项目，停止并请求扩展授权，不借本任务代做INFRA/FE。

上述是未来任务的拟议所有权，不是本次归档的可写范围。不创建`packages/ui`直到ADR决定明确；也不删除或降级Design System能力。

### 输出与验收

- 工程命名、根配置、局部工具及依赖版本清单可审查；无浮动版本、全局旧EF依赖或凭证。
- AGENTS/PLANS明确授权门禁、模块边界、任务交接、注释、禁用项和验证证据；Next管理区块与根规则分离。
- CI至少能运行仓库规则和配置校验。尚无业务项目的build/test明确报告NOT_RUN及原因，不以空solution或零测试成功冒充功能通过；随下游项目落地接入真正构建测试。
- `doctor`报告版本、批准工具可用性及环境限制；只读检查不自动安装或启动资源。`verify`按存在且获准的目标调用原生工具，缺失目标明确标记。
- 记录独立审查意见、实际命令/退出码、差异和遗留项；不提交不完整或误导的锁文件。

### 测试计划（均NOT_RUN）

1. 检查命名、workspace范围、配置语法、相对链接及Git白名单；禁止包、绝对路径和秘密扫描。
2. 在获准环境复核SDK/Node/pnpm/局部EF版本；验证锁定恢复与版本不匹配的失败路径。需要安装/restore时先核对后续专用授权是否覆盖。
3. 用正反例验证工程规则能识别违规配置；注释自定义检查只宣称实际覆盖范围。
4. 核查AGENTS与`.codex`当前客户端兼容性和加载范围；说明不等同沙箱或永久权限。
5. 独立Reviewer复核范围、许可及证据；只报告实际执行检查，应用/E2E/基础设施测试保留NOT_RUN。

### 停止条件

- 未获专用G1授权、关键ADR未决、发现未预期改动或任务需要越出白名单：停止并报告。
- 需要未批准依赖、凭证、数据库、容器启动、业务源码或额外工程：停止对应工作，不自动扩权。
- 完成本任务和独立审查后提交证据，等待Master/用户下一项明确授权；不自动启动G1-INFRA-001、G1-SEC-001、G1-FE-001、G1-OBS-001或G2。

## 任务卡样例

```yaml
id: G2-PUB-001
title: 不可变本体发布与回滚
status: proposed
owner: semantic-backend-owner
reviewer: independent-quality-reviewer
depends_on: [G2-SEM-001, G1-SEC-001]
owned_paths:
  - backend/src/Modules/Publishing/**
read_only_dependencies:
  - backend/src/Modules/Ontology/**
  - docs/contracts/**
contracts:
  - OntologyReleaseManifest
  - AssetVersionSnapshot
acceptance:
  - 未审核或修订变化不得激活
  - 外部部署失败保持旧active
  - 重复命令及提交响应丢失可安全恢复
  - 回滚不破坏固定旧快照的运行
tests:
  - release-faults
  - release-rollback
  - authorization
observability: [audit, traces, metrics, structured-logs]
deliverables: [source, contracts, tests, evidence, operations-docs]
```

所有任务继承原合同完整DoD。公共合同变更先提建议，由指定作者合并；审查失败回到原Owner，不由Reviewer越界代改。
