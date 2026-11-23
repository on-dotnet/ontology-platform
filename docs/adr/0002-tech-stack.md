# ADR 0002：技术栈

- 状态：已采纳（2026-11-22）

## 决策

| 层 | 选型 | 主要理由 |
|---|---|---|
| 后端语言与框架 | Python 3.13 + FastAPI（模块化单体） | AI、语义网、文档解析、数据库驱动的生态都在 Python，一种后端语言覆盖全部；同类开源项目的贡献者主要使用 Python |
| 语义处理 | rdflib、pySHACL、owlrl，进程内运行 | 解析、校验、OWL 2 RL 推理无需远程往返；均为持续维护的成熟库 |
| 本体存储 | PostgreSQL 中按元素存储，发布时生成 RDF 快照 | 差异、审核、AI 提议都以元素为单位；对外仍是 W3C 标准 |
| 图存储 | M3 起按需引入 Oxigraph，经 SPARQL 标准协议访问 | 前期用不到；协议标准化，可替换为 Fuseki、GraphDB |
| 数据源 | 统一连接器接口，基于 SQLAlchemy 方言（PG、Oracle thin、Doris 走 MySQL 协议、TDengine）；Web 走 HTTP | 目录发现、只读、超时、取消只实现一次 |
| AI | OpenAI 官方 Python SDK 的 Responses API 结构化输出（模型可配置），经平台自己的 `ModelGateway` 接口调用；pgvector 做向量检索 | 结构化输出有类型校验；可切换到私有或其他兼容 OpenAI 接口的模型；网关一层便于记录用量、换实现和在测试里替身 |
| 文档解析 | 纯 Python 轻量解析（docx、xlsx、pptx、文本型 PDF）；扫描件与复杂 PDF 交给多模态模型 | 当前开发主机无 AVX，本地 OCR 与 torch 不可用；有条件后可加 Docling |
| 后台任务 | 基于 PostgreSQL 的任务队列 | 不额外引入 Redis |
| 认证 | 内置账号 + 可选 OIDC | 开源用户一条命令即可运行；企业可接入统一认证 |
| 前端 | React 19 + Vite + TanStack Router/Query + Tailwind 4 + Base UI（shadcn/ui 写法）+ i18next | 管理后台不需要服务端渲染，构建与部署更简单 |
| 运行 | Docker Compose + `dev.ps1` | 代码在本机、容器在 Docker 主机，与 hlc-iov 一致 |

## 修订

- 2026-11-23（M1）：AI 层原定"OpenAI Responses API + pydantic-ai"。M1 的分阶段抽取只需要"指令 + 文本 → Pydantic 结构"的单次调用，官方 SDK 的 `responses.parse` 已直接支持，再加一层框架只增加依赖和排错成本，因此改为直接用官方 SDK。pydantic-ai 等智能体框架推迟到 M2 的问答与智能体功能时再评估。

## 被否决的方案

- **保留 .NET**：OWL/SHACL 生态只有 dotNetRDF，缺少 OWL 推理；文档解析仍需 Python。
- **TypeScript 全栈**：前后端同语言，但 OWL 推理与数据驱动生态较弱。
- **以三元组库为唯一存储**：审核、差异、并发编辑和 AI 候选在关系模型中实现更简单。

## 约束

- 新依赖须是许可证宽松（MIT、Apache-2.0、BSD、ISC、OFL 等）的知名开源库，在 PR 中写明来源、版本和许可证。
- 例外：PostgreSQL 驱动 psycopg 3 是 LGPL-3.0。我们以未修改的方式通过 Python 导入动态使用它，不分发修改版，与 Apache-2.0 项目兼容（同类做法如 Apache Airflow）。其他弱著作权（LGPL、MPL）依赖按同样条件逐个在 PR 中说明；强著作权（GPL、AGPL）依赖不引入。
- 在 Docker 主机 CPU 升级前，不引入需要 SSE4.2/AVX 的包（例如 NumPy ≥ 2.4、torch、polars）。
