# 架构说明

本文是现行架构的唯一说明。重大取舍记录在 [docs/adr](adr/)，界面规则见 [ui-guidelines.md](ui-guidelines.md)，阶段计划见 [roadmap.md](roadmap.md)。

## 1 产品定位

AI Native 的本体智能平台：把企业的资料、数据和专家经验整理成可治理的本体（业务概念、关系、约束、术语），再让人和 AI 基于本体查询、分析和决策。

- **AI 优先**：建模、数据绑定、问答都由 AI 先提议，人审核后生效。手工编辑是补充。
- **标准语义**：对外使用 W3C 标准（RDF、OWL 2、SHACL、SKOS、PROV-O），可与 Protégé 等工具互通。
- **通用平台，行业案例驱动**：平台本身不含行业概念；钢铁冶金是第一个案例包（[samples/steel](../samples/steel)）。
- **私有化与开源**：Apache-2.0，一条命令在本地或企业内网跑起来。

## 2 核心闭环

```
资料 / 数据表 / 对话
      ↓  AI 提议（每条带证据原文与置信度）
   变更集  ←── 人也可以直接编辑
      ↓  逐项审核：接受 / 修改 / 拒绝
   本体工作版本 → 校验（SHACL、一致性、影响）→ 发布版本（不可变，可回滚）
      ↓
   使用：对象查询、AI 问答、MCP、指标规则
      ↓  发现缺口（问不出、对不上）
   AI 再提议 ─┘
```

**变更集（ChangeSet）是唯一的写入通道。** 无论来源是 AI 识别、AI 对话、AI 绑定建议、外部智能体经 MCP 的提议还是人工编辑，对本体的修改都先成为变更集里的操作（新增、修改、删除某个元素），每个操作带来源与证据；审核通过后合并进工作版本。AI 没有直接写本体的权限。

**数据绑定走同一条通道（M3）。** 对象类型对表、属性对列、关系对外键的绑定也是变更集里的操作，审核合并后进入工作版本，发布时随版本固化。对象查询和 MCP 只使用当前生效的发布版本及其绑定：没有审核、没有发布的绑定查不到数据，回滚版本时绑定跟着回滚。

## 3 本体模型

本体在 PostgreSQL 中按"元素"存储，发布时生成标准 RDF 快照。

| 元素 | 含义 | 标准映射 |
|---|---|---|
| 对象类型 EntityType | 业务概念，如"炉次""板坯" | `owl:Class` |
| 属性 Property | 对象的数据字段，含数据类型、单位、必填、基数 | `owl:DatatypeProperty` + SHACL `sh:property` |
| 关系类型 RelationType | 对象之间的关系，含方向、基数、互逆 | `owl:ObjectProperty` |
| 层级 | 类型的父子关系 | `rdfs:subClassOf` |
| 约束 Constraint | 校验规则；常见约束由属性定义自动生成 | SHACL |
| 术语 Term | 中英文名称、同义词、定义 | `rdfs:label`、SKOS |
| 其他语句 Other statements | 表单无法表达的 SHACL 形状、OWL 逻辑公理、实例或代码、多余的父类型、注解及其他三元组 | 原样保存的 Turtle 片段，可在专家模式编辑 |
| 数据绑定 Binding（M3） | 类型绑定（对象类型对表或视图加主键列）、属性绑定（属性对列）、关系绑定（关系对外键或连接表） | 不进 OWL 导出；可另行导出为 R2RML |

- 每个元素有稳定 IRI，名称与 IRI 分离，改名不改 IRI。数据绑定和其他语句没有自己的 IRI。
- 数据绑定与其他元素存在同一张表里、走同一套审核，但不属于本体的语义内容：导出、导入、差异、图谱、AI 识别都只看语义元素，取舍见 [ADR 0003](adr/0003-data-binding-and-external-access.md)。
- 导入外部 OWL 时，能映射的进入元素表，映射不了的作为其他语句原样保留，保证"导入再导出不丢内容"。
- 每个元素和每次变更都记录来源（人或某次 AI 运行）、证据（资料片段、数据样本）和时间（PROV-O）。

## 4 模块

后端是一个 Python 模块化单体。模块之间只通过各自的服务接口调用，不跨模块读写表。服务接口交给其他模块的只是普通数据（冻结的 schema 或 dataclass），不交出 ORM 实例，以免其他模块绕过本模块写表（由 `backend/tests/test_module_boundaries.py` 检查）。

| 模块 | 职责 | 里程碑 |
|---|---|---|
| identity | 账号、会话、角色、登录登出、CSRF；访问令牌（M3） | M0、M3 |
| audit | 审计事件 | M0 |
| ontology | 本体、元素、变更集、审核、版本、发布、导入导出、校验；数据绑定及其已发布的只读视图（M3） | M1–M3 |
| documents | 资料上传、存储、解析、片段与锚点 | M1 |
| ai | 模型网关、抽取流水线、建模助手、绑定建议（M3）、问答智能体、评测 | M1–M4 |
| connectors | 数据源与加密的凭据、统一连接器接口、目录发现与缓存、只读执行。M3 只有 PostgreSQL 连接器。只有这个模块可以连接外部数据源 | M3 |
| query | 按本体查询对象：把请求编成结构化的查询交给 connectors 执行；列表、详情、沿关系走一跳，结果带来源 | M3 |
| mcp | 对外 MCP 服务（只读工具 + "提议变更"工具），工具与传输分开 | M3 |
| metrics | 指标与规则 | M4 |
| jobs | 基于 PostgreSQL 的后台任务队列 | M1 |

目录约定：`backend/src/ontology_platform/modules/<模块>/`，每个模块内按 `models.py`（表）、`schemas.py`（接口模型）、`service.py`（业务逻辑）、`api.py`（路由）组织；需要时再拆子目录，不预建空层。

## 5 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.13、FastAPI、Pydantic 2、SQLAlchemy 2（异步，psycopg 3）、Alembic、uv |
| 语义 | rdflib、pySHACL、owlrl（进程内） |
| AI | OpenAI 官方 SDK 的 Responses API 结构化输出（模型可配置，经 `ModelGateway` 调用）；向量检索用 pgvector |
| 存储 | PostgreSQL 18 + pgvector；资料原件存本地卷（可切换 S3 兼容存储） |
| 数据源（M3） | SQLAlchemy Core 生成只读语句、Inspector 做目录发现；PostgreSQL 用 psycopg 3；凭据用 `cryptography` 的 AES-256-GCM 加密。M3 不引入 Oxigraph、SPARQL、Ontop |
| 对外（M3） | MCP 2026-07-28（无状态，Streamable HTTP），在 FastAPI 里直接实现；访问令牌认证 |
| 前端 | React 19、TypeScript、Vite、TanStack Router 与 Query、Tailwind CSS 4、shadcn/ui 风格组件（Base UI）、lucide 图标、i18next |
| 运行 | Docker Compose；`dev.ps1` 统一入口 |

选型理由见 [ADR 0002](adr/0002-tech-stack.md)；M3 的部分见 [ADR 0003](adr/0003-data-binding-and-external-access.md)。

## 6 运行拓扑

```
浏览器 ────────┐
               ├─► web（nginx，静态页面 + 反向代理 /api、/mcp）──► api（FastAPI）──► postgres（pgvector）
外部智能体 ────┘                                                   │  └──► worker（M1 起，后台任务）
（MCP，M3）                                                        └──► 用户的数据源（M3，只读）
```

- 对外只发布 web 的端口（开发环境默认 28080）。api、postgres 只在 compose 网络内可达。
- 用户的数据源由 api 和 worker 直接连接，只读（第 8 节）。开发环境的样例数据源是同一个 postgres 实例里的另一个库 `steel_mes`，用只读账号访问（`./dev.ps1 seed-steel`）。
- 开发环境：代码在 Windows 本机，容器跑在 Docker 主机 10.16.0.13，见 [development.md](development.md)。

## 7 接口约定

- 前缀 `/api`，JSON，字段用 camelCase。OpenAPI 文档由后端生成，前端类型由它生成（`./dev.ps1 gen-api`）。
- **错误**一律返回 `application/problem+json`（RFC 9457）：`{ type, title, status, detail, code }`。`code` 是稳定的机器码（如 `auth.invalid_credentials`），前端按 `code` 显示本地化文案，不直接显示后端原文。
- **认证**：服务端会话。登录成功后下发 `op_session`（HttpOnly、SameSite=Lax，生产环境 Secure）。会话存在数据库，只保存令牌的 SHA-256。默认空闲 8 小时过期。
- **CSRF**：双提交令牌。登录后下发可被脚本读取的 `op_csrf` Cookie；所有写请求（POST/PUT/PATCH/DELETE，登录除外）必须带同值的 `X-CSRF-Token` 头。
- **访问令牌（M3）**：给外部程序用。请求头 `Authorization: Bearer op_pat_…`；库里只存 SHA-256，全文只在创建时显示一次；有作用域、过期时间，可撤销。带令牌的请求只按令牌认证、不走 CSRF。`/api` 的路由默认不接受令牌，只有声明了作用域的读接口接受；令牌唯一的写入口是 MCP 的"提议变更"工具。
- **MCP（M3）**：`POST /mcp`，JSON-RPC，按 MCP 2026-07-28 规范（无状态），不在 `/api` 下，用访问令牌认证。规范里可选的 OAuth 2.1 授权不在 M3，放 M5。
- **分页**：`?limit=&cursor=`，响应 `{ items, nextCursor }`。
- **时间**：ISO 8601，带时区，存储用 UTC。

错误码（前端按码显示本地化文案）：

| code | HTTP | 含义 |
|---|---|---|
| `auth.invalid_credentials` | 401 | 用户名或密码错误、账号已停用（不区分，防止枚举） |
| `auth.not_authenticated` | 401 | 未登录或会话已过期 |
| `auth.csrf_failed` | 403 | 写请求缺少或带错 CSRF 令牌 |
| `auth.forbidden` | 403 | 角色不足 |
| `auth.invalid_token`（M3） | 401 | 访问令牌不存在、已过期、已撤销，或主人已停用 |
| `auth.token_not_allowed`、`auth.insufficient_scope`（M3） | 403 | 接口不接受访问令牌；令牌缺少所需的作用域 |
| `validation.failed` | 422 | 请求参数不合法，附 `errors` 列表（不回显输入值） |
| `health.not_ready` | 503 | 数据库不可用 |
| `http.not_found`、`http.method_not_allowed` | 404、405 | 路径或方法不存在 |
| `internal.error` | 500 | 未预期的错误，不返回内部细节 |

M0 的接口：

| 方法与路径 | 说明 |
|---|---|
| `GET /api/health` | 存活检查，不查库 |
| `GET /api/health/ready` | 就绪检查，查库 |
| `POST /api/auth/login` | `{ username, password }` → 用户信息；写会话与 CSRF Cookie |
| `POST /api/auth/logout` | 注销当前会话 |
| `GET /api/auth/me` | 当前用户；未登录返回 401 |

## 8 安全

- 对外部数据源只读，有两道独立的防线（M3）：
  - 平台只执行自己从已发布的绑定生成的参数化 SELECT，不接受用户或模型写的 SQL；只有 connectors 模块可以连接外部数据源。
  - 连接层一律是只读会话加只读事务，带语句超时、行数上限，可取消。
- 连接凭据用 `OP_SECRET_KEY` 派生的密钥加密保存（AES-256-GCM，绑定到数据源 id），任何接口、日志、审计、错误信息都不回显；密钥轮换用 `OP_SECRET_KEY_PREVIOUS` 过渡。平台自己的数据库不能作为数据源。
- 发给模型的数据源信息默认只有表名、列名、类型和注释；样本值由数据源上的开关控制，默认关（M3）。
- 数据的可见范围，是 M3 的已知限制（行级和列级权限、界面查询的逐条审计放 M5）：
  - 绑定并发布的列，数据对所有登录用户可见；对象查询不会读取没有绑定的列。
  - 被提议绑定或已经绑定的表名、列名、注释随变更集对所有登录用户可见，包括后来被拒绝的建议；浏览数据源的整个目录需要 editor 以上。
  - 样本值开关打开时，AI 绑定建议会读取候选列（包括还没绑定的列）的少量取值，这些取值作为证据随变更集对所有登录用户可见。
- 密码用 Argon2id；首次启动若无账号，用环境变量创建管理员（开发环境有固定默认值，生产环境必须显式设置）。
- 角色：`admin`（管理）、`editor`（编辑与提议）、`reviewer`（审核与发布）、`viewer`（只读）。是否要求"提议人与审核人不同"由配置决定，默认单人模式允许自审，企业模式要求异人审核。
- 模型 API Key 只通过环境变量或不入库的文件提供，不写进代码、日志和数据库。
- 识别资料时，平台会将资料正文和扫描件原件发送给配置的模型服务。平台默认通过 `store=false` 请求服务端不保存响应，实际留存策略由服务方决定。平台自己的 `ai.runs` 表不保存提示词和资料原文。
- 审计：登录、登出、变更集提交与审核、发布、回滚、连接配置变更都写审计事件。M3 起还有：连接测试、读取目录、读取样本值、发起 AI 绑定建议、访问令牌的创建与撤销及被拒、每次 MCP 工具调用。
- 客户端 IP：api 只信任 web 容器的 nginx，nginx 用实际对端地址覆盖 `X-Forwarded-For`。若生产环境在 nginx 前还有负载均衡，需要在 nginx 配置 `set_real_ip_from` 指向负载均衡的地址段，否则审计里记录的是负载均衡的 IP。
- 登录防护：nginx 对登录接口按 IP 限流（超限返回 429 `auth.rate_limited`）；后端限制同时进行的密码哈希数；用户不存在时也执行一次哈希，使响应耗时一致。
- 生产环境启动校验：`OP_SECRET_KEY` 至少 32 个字符，管理员密码至少 12 个字符，数据库口令不能是开发默认值；会话 Cookie 默认带 Secure。

## 9 身份认证

- 默认：平台内置账号与登录页，和平台使用同一套设计系统。
- 可选：接入企业 OIDC（Keycloak 或其他 IdP）。接入 Keycloak 时，用 Keycloakify 以同一套 React 组件和设计令牌生成登录主题，保证风格统一（见 [roadmap.md](roadmap.md)）。
