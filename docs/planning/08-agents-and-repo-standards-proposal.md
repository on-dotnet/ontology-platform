# 08 · AI Native工程结构与根配置提案

本文件全部工程布局和配置均为 **PROPOSED**，尚未落地；仅本文档归档获准。状态与授权见 [10](10-g0-review-record.md)。

## 目录方案

以下是目标布局，按阶段创建实际需要的部分，不提前生成空模块工程。

```text
ontology-platform/
├─ AGENTS.md
├─ PLANS.md
├─ .agents/
│  └─ skills/                         # 可重复研发流程
├─ .codex/
│  ├─ config.toml                     # 项目研发配置
│  └─ agents/                         # Codex研发角色
├─ .github/
│  ├─ workflows/
│  ├─ CODEOWNERS
│  ├─ ISSUE_TEMPLATE/
│  └─ pull_request_template.md
├─ .config/dotnet-tools.json
├─ apps/
│  └─ web/                            # @ontology-platform/web
│     ├─ AGENTS.md
│     ├─ package.json
│     ├─ next.config.ts
│     ├─ eslint.config.mjs
│     ├─ tsconfig.json
│     ├─ components.json
│     ├─ postcss.config.mjs
│     ├─ public/
│     ├─ src/
│     │  ├─ app/
│     │  ├─ features/
│     │  ├─ components/ui/
│     │  ├─ components/shell/
│     │  ├─ lib/api/generated/
│     │  ├─ hooks/
│     │  └─ styles/
│     └─ tests/
├─ backend/
│  ├─ AGENTS.md
│  ├─ OntologyPlatform.slnx
│  ├─ src/
│  │  ├─ Hosts/OntologyPlatform.Api/
│  │  ├─ AppHost/OntologyPlatform.AppHost/
│  │  ├─ ServiceDefaults/OntologyPlatform.ServiceDefaults/
│  │  ├─ BuildingBlocks/
│  │  │  ├─ OntologyPlatform.BuildingBlocks.Abstractions/
│  │  │  └─ OntologyPlatform.BuildingBlocks.Infrastructure/
│  │  └─ Modules/
│  │     ├─ Ontology/
│  │     ├─ Terminology/
│  │     ├─ SemanticValidation/
│  │     ├─ Publishing/
│  │     ├─ Connections/
│  │     ├─ EntityGraph/
│  │     ├─ SemanticQuery/
│  │     ├─ MetricsRules/
│  │     ├─ Knowledge/
│  │     ├─ Agents/                    # 产品运行时MAF/Run/工具
│  │     ├─ Applications/
│  │     └─ Governance/
│  └─ tests/
│     ├─ OntologyPlatform.ArchitectureTests/
│     ├─ OntologyPlatform.ContractTests/
│     ├─ OntologyPlatform.IntegrationTests/
│     └─ Modules/
├─ workers/document-processing/
├─ semantic/                          # 正式RDF/OWL/SHACL/SKOS源资产
├─ samples/metallurgy/                # 行业本体、可信样例和Eval
├─ infra/                             # 部署、观测、备份恢复
├─ scripts/                           # 开发、跨语言构建与验收入口
├─ docs/
│  ├─ bootstrap/
│  ├─ planning/
│  ├─ adr/
│  ├─ contracts/
│  ├─ tasks/
│  └─ evidence/
├─ global.json
├─ Directory.Build.props
├─ Directory.Packages.props
├─ NuGet.Config
├─ package.json
├─ pnpm-workspace.yaml
├─ pnpm-lock.yaml
├─ turbo.json
├─ .node-version
├─ .editorconfig
├─ .gitattributes
├─ .gitignore
├─ .dockerignore
└─ .env.example
```

所有.NET项目和namespace使用`OntologyPlatform.*`。普通模块实现项目命名为`OntologyPlatform.Modules.<Module>`；必要的Domain/Contracts项目追加相应后缀。

## 四类共享能力边界

| 位置 | 职责 | 提取条件 |
|---|---|---|
| `apps/web/src` | 当前应用UI、Hooks、生成客户端和前端共享逻辑 | 第二真实消费者出现后再评估独立包 |
| `backend/.../BuildingBlocks` | 必要跨模块技术合同及设施 | 有多个真实消费者且职责稳定 |
| `backend/.../ServiceDefaults` | 宿主启动、OTel、健康、发现和HTTP弹性 | 不放业务模型及规则 |
| `backend/.../Modules/Agents` | 产品MAF、Run、模型路由、受控工具 | 按产品用例实施 |
| `.agents/skills`、`.codex/agents` | 研发流程与Codex角色 | 不进入产品运行时依赖 |

**优化提议，待ADR-001明确批准：暂不建立根`packages/`及`packages/ui`，pnpm workspace暂只声明`apps/web`。** Turbo负责前端任务图，根脚本显式协调dotnet、语义检查及Worker。[Turborepo结构说明](https://turborepo.dev/docs/crafting-your-repository/structuring-a-repository)

暂缓共享包不能覆盖先前Design System决策。设计Tokens、可复用组件、Shell、主题、可访问性和统一交互规范仍必须建立；当前提议先在`apps/web/src/components/ui`、`src/styles`维护。ADR须说明单消费者收益、未来提取路径、导入边界、版本/主题契约、测试和迁移成本，并列出直接采用`packages/ui`的备选。未决时不得将此提议写成已批准实施事实。

## 根级构建配置

| 文件 | 具体约定（PROPOSED） |
|---|---|
| `global.json` | SDK10.0.402、`allowPrerelease:false`、`rollForward:"disable"`；MTP runner经PoC固定 |
| `Directory.Build.props` | net10.0默认、Nullable、ImplicitUsings、确定性构建、分析器和XML文档；C#随固定SDK，不用`latest` |
| `Directory.Packages.props` | NuGet集中版本；项目引用不重复版本 |
| `Directory.Build.targets` | 仅在自定义命名/注释校验落地时增加，不先建立空文件 |
| `NuGet.Config` | 明确源和必要source mapping；不存凭证 |
| `.config/dotnet-tools.json` | 局部dotnet-ef10及批准工具，禁止依赖机器全局版本 |
| 根`package.json` | `private:true`，根名`ontology-platform`，固定packageManager，提供前端任务入口 |
| `pnpm-workspace.yaml` | ADR-001推荐方案为精确包含`apps/web`，无默认`packages/*`，等待单项批准 |
| `turbo.json` | build/lint/typecheck/test分离；dev不缓存且持续；集成/E2E不缓存 |
| `.node-version` | Node24 LTS精确补丁与CI/镜像一致；G1兼容验证后锁定 |
| `.editorconfig` | C#4空格、Allman、成员间空行；TS/JSON2空格；UTF-8及统一换行 |
| `.gitattributes` | 明确文本换行和二进制资产，避免跨平台无效差异 |
| ignore文件 | 排除构建物、运行状态、密钥、日志及本地凭证，保留可审查工程配置 |
| `.env.example` | 仅变量说明和无敏感示例，真实凭证由安全配置注入 |

SDK固定、CPM和依赖锁定分别承担不同职责。[global.json](https://learn.microsoft.com/en-us/dotnet/core/tools/global-json)、[集中包管理](https://learn.microsoft.com/en-us/nuget/consume-packages/central-package-management)

可执行入口、AppHost和测试工程提交`packages.lock.json`；CI locked restore。类库自身锁文件不决定消费者最终依赖图。[NuGet锁定说明](https://learn.microsoft.com/en-us/nuget/consume-packages/package-references-in-project-files)

Next采用`src/app`，业务切片放`src/features`，图编辑器和Monaco明确客户端边界。生产使用standalone；有真实跨应用追踪需求时才扩大output tracing root。[目录说明](https://nextjs.org/docs/app/getting-started/project-structure)、[standalone说明](https://nextjs.org/docs/app/api-reference/config/next-config-js/output)

## AGENTS、技能和角色

根`AGENTS.md`建议正文要点：

```text
项目身份：on-dotnet/ontology-platform；所有.NET标识使用OntologyPlatform.*
先读取当前批准计划、任务卡及适用目录指令。
仅执行已授权关口；G0不得写代码、安装、迁移或部署。
遵守冻结技术和禁用项；新增依赖或偏离方案先走ADR/审批。
修改前检查Git状态；保留用户改动。
严格遵守模块写入边界、公共契约Single Writer和任务目录所有权。
执行与变更相关的验证，记录命令、退出码及NOT_RUN。
交付同步API、测试、审计、观测和恢复说明。
独立审查后由Master集成；未获批准不得进入下一关口。
详细规范见PLANS.md、docs/adr、docs/contracts及目录AGENTS。
```

`apps/web/AGENTS.md`保留Next管理区块，另列设计、SSR、权限、SSE和真实交互规范；`backend/AGENTS.md`写模块、注释、事务和原生框架规范；Worker/语义目录在引入时补充专项规则。由仓库根调度任务时，任务卡显式要求读取目标目录指令，避免假定所有嵌套规则自动加载。

`.agents/skills`首批候选为`verify-change`、`semantic-release-check`、`contract-change`；只在对应流程形成可运行入口后创建。不得把完整合同复制进每个技能。

`.codex/agents`首批提案为只读explorer、semantic-reviewer、quality-reviewer及范围受限worker。当前可识别角色字段示例：

```toml
name = "semantic_reviewer"
description = "只读检查语义保真、版本和发布恢复风险。"
developer_instructions = """
不得修改文件。
引用实际证据；区分OBSERVED、NOT_FOUND、NOT_VERIFIED。
检查公理保真、权限、版本一致性及恢复路径。
"""
```

角色说明不是沙箱隔离，也不是永久Master权限。项目配置不覆盖组织策略，不嵌入生产MCP凭证；实际加载及只读限制在G1做兼容验证。

`PLANS.md`定义批准记录、任务卡、依赖、决策日志、上下文交接、验收证据和关口退出规则。

## GitHub、注释和质量规范

- CI分为前端、后端、语义、集成和供应链检查；动作与容器固定可追溯版本，权限最小化，受保护环境单独审批。
- CODEOWNERS覆盖公共契约、迁移、Tokens、安全和部署；PR模板要求任务ID、行为变化、执行证据、NOT_RUN及回滚影响。
- C#全部手写成员及局部变量遵循原合同中文说明要求；自动生成文件明确豁免。
- `CS1591`仅强制其可覆盖的公开成员。私有成员、局部变量及成员空行采用必要的自定义检查和人工评审；G1先以正反样例验证检查能力，不能以空注释制造覆盖率。
- 前端重要组件、Hooks、领域类型和复杂算法使用中文业务JSDoc/TSDoc。
- shadcn采用应用内组件、暂不使用自动建立共享UI包的monorepo预设，仍属ADR-001待批提议；视觉自主实现，商业模板仅作风格参考。
- UI保留Next.js + shadcn/ui + Base UI及Tailwindadmin风格彩色企业后台。Rhea仅作为**待核实的组件风格参考（NOT_VERIFIED）**，不是新增依赖，不替代自研Tokens，不编造已验证资产。
