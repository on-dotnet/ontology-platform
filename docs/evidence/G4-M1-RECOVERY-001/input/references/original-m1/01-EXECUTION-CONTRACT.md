# G4-M1-CONNECTION-001 · 正式执行合同 V1.0（提案，待人类授权）

## 1. M1 最终要交付什么

本阶段不是又一轮资料整理。获批准后 Codex 应完成一个**真实可操作的 PostgreSQL 纵向链路**：Keycloak 受权管理员登录 → 选择 PG → 表单校验 → 专用密钥输入生成 SecretRef → 测试未保存草稿（网络/TLS/认证/只读/metadata） → 创建草稿 → 保存与重载 → 已保存对象复测 → 有效 Probe 后启用 → Catalog Schema 发现/快照/刷新 → 编辑使旧 Probe 失效 → 再测 → 禁用/拒绝后续动作 → 操作审计、故障/恢复。只有测试通过和新的认证/配置仍一致才可启用。

同一个入口包含五源类型动态参数表单，Oracle/Doris/TDengine/Web API 先实现**受 Schema 约束的真实前端交互**，但“测试/保存到可用连接”的后端能力在 M2 前必须明确 `CONNECTOR_NOT_IMPLEMENTED` / `NOT_AVAILABLE`，不得假装五源联通通过。

成功条件不是 200 响应或按钮变色，而是全链条有真实 DB、HTTP/OIDC、浏览器、证书负例、CAS、隔离及回收证据。所有产品结果由未来 Codex 运行产生，本包没有真实产品 PASS。

## 2. 工作分解与出关门禁

| 关口 | 输出 | 必须先完成的证明 | 失败处置 |
|---|---|---|---|
| P0 Preflight | Base/Worktree/现有包/API/G3授权与资源; Npgsql+PG镜像/证书可用性 | 命令选项真实存在，已审依赖可获取；不得改旧数据 | 缺条件标 BLOCKED；继续非依赖设计 |
| P1 Wire Freeze | DTO/API/命令/HTTP 401/403/409/422/503、Secret、Probe、Catalog、状态机/源端ACL | 独立 Reviewer 先审正反例；设计脚本PASS | P1 FAIL 不派写，不默认扩合同 |
| P2 并行产品切片 | PG Adapter/业务模块；五类UI表单；Master Host/Contract/EF/schema/Dev Compose | 编译/定向单测，代码所有权无交叉 | 缩小失败，不全量反复跑 |
| P3 First Integration | PG TLS+权限的真实服务; 登录至创建/测试/禁用最短链 | backend真实PG + 权限负例 + HTTP 已测 | 问题修复后早cherry-pick任务分支，不是main |
| P4 Second Integration | Catalog持久Job、UI状态/刷新、审计故障恢复 | 已保存连接的Probe与Catalog闭环; 脱敏/撤权 | 修改真实受影响层，旧证据保留 |
| P5 Complete Local Acceptance | M1测试矩阵、运行资源收尾、独立最终 Review | 稳定输入完整产品E2E、安全/故障、证据链、唯一V3重开 | 不满足则PARTIAL/BLOCKED，不虚报PASS |

先单写公共合同，后最多两个独立写者。Codex Master唯一产品集成，不在第一次集成之前积压全部修改。实验默认遵从当前仓库已批准 local-validation-policy：CI按需手动，不运行记 NOT_RUN，不因为任何证据提交重复全量 E2E。

## 3. 单一产品事实来源

G4新增 DTO 由 `backend/src/Contracts/OntologyPlatform.Contracts` 的唯一 Owner + `docs/contracts` 明确权威，再经后端实际 OpenAPI → 前端 TS 类型生成。仓库原有 G2/G3 `g2-models.json` 与 `G2Models.g.cs` 是冻结事实，**M1不得向旧 JSON 追加自创本体或修改 G2 模型语义**。本包 `contracts/*.schema.json` 是待实现接口的设计测试规范，不是权威域语义模型，也不提供第二个产品 codegen 源。

G4 与 G3 共用可信 `ActorContext`、scope、CSRF/OIDC/Guard、治理审计及单次PG事务原则；新业务只在 `Connections` 所属 schema 存元数据。源业务表不归 EF 管理，绝不迁移源数据库。

## 4. M1 具体用户旅程

1. 管理员通过服务器身份获取可管理组织厂区（不能信客户端org/site），打开列表看到经授权的连接；没有权限显示 403/隐藏入口而非空成功。
2. 新建向导类型卡片变化触发不同必填参数；PG 输入 host/port/database/username/sslMode/allowedSchemas，默认 VerifyFull，证书信任不由客户端任意上传路径。
3. Secret仅通过 `POST /api/v1/connection-secrets` 专门受控提交；Server返回短寿命单次 `secretRef`，不会在列表/详情响应重显密钥。临时 secret 未绑定时到期/安全清理。
4. `POST /api/v1/connections/tests` 对未保存草稿执行分阶段真实PG只读 Probe，不落正式连接；用“配置+secretVersion+scope+target+时间”绑定结果。
5. `POST /api/v1/connections` 使用唯一 `config:{type,profile}`、顶层`secretRef`、`CommandContext.expectedRevision=0`，事务审计；创建仅 DRAFT，不自动启用。
6. 对已有连接 `POST .../{id}/test` 获得 Probe；`GET .../probes/{id}` 查看分阶段结果；未完全通过不得启用。
7. 通过 `POST .../{id}/enable` 显式启用；配置更新 `PATCH` 必须 If-Match+正修订并使 Probe 过期；轮换Secret单独命令；本轮禁止通过保存/测试自动启用。
8. `POST .../{id}/discoveries` 创建有界持久发现Job；`GET .../{id}/discoveries/{jobId}`/`GET .../{id}/catalogs`/`GET /api/v1/catalogs/{snapshotId}` 完成可恢复Schema目录，0对象、权限不足、部分成功分别显示不同结果。
9. `POST .../{id}/disable` 停止新的任务与源访问，进行中的任务按持久取消/终态策略处理；保存历史审计和Catalog引用，但不能继续以旧结果访问撤权源。

## 5. 安全、权限与安全默认

- 五源中仅 PG Adapter truly ENABLED，源账号只具授权 schema/表的 SELECT 及 metadata 必需权限；SQL执行由服务器固定白名单对象/查询、参数值和限制，用户绝无自由 SQL；根本不存在生产源写回端点。
- 成功 Probe 要证明连接/TLS+认证/源端角色及合法目录能力；TCP通但权限不够不算TEST_OK。测试源是隔离 synthetic，不用破坏性 DML 探测权限。
- OIDC、CSRF、If-Match、resource based scope 与 `connection.read/manage/test/secret.manage/schema.read/discover` 明确配置，任何新权限默认不对 viewer 自动授予，管理员不因为能配源而自动取得生产数据读取权。
- 禁止跨厂、多租户、角色越权；`SecretRef` 一次性、受组织/操作者/用途/过期/版本约束；没有 Dev vault 实物就不允许假测试通过。
- 不读取真实业务样本行；M1 schema 发现仅 metadata，若收到表/列注释按不可信文本处理，不发送外部LLM。AI模式默认OFF；不能声称 AI 查询已经实现。

## 6. 兼容范围与出口

G2 `POST /api/v1/semantic/queries` 的十一字段原结果、已有三 MCP工具、G3正式 RDF/OWL/SHACL及 Release 不能变。M3 `MappingProposalView` 回滚判别DTO、M4 `G4SemanticDatum` 完整 observation/value/unit/time 仍 BLOCKED_FOR_IMPLEMENTATION；本次不得误写新类型跨越这些门禁。

若 M1 完成：本任务 Reviewer PASS、适用完整真实本地验收、唯一 V3 完整/独立重开、主线受保护、资源准确收尾。输出 `G4_M1_CONNECTION_READY_FOR_CHATGPT_REVIEW` 并停止。若真实 TLS/许可/镜像/宿主/依赖不可满足，输出 `G4_M1_CONNECTION_BLOCKED_WITH_WITNESS`，附最小精确授权/环境需求与已完成其余部分，不宣称产品PASS。

## 7. 代码目录与接口设计不对外过度承诺

实际 namespace、EF schema/表、Public DTO、API paths、权限名以 P1 合同冻结的文件+测试为唯一产品实物。不可为了路径标准化而破坏G2已运行端点。前端保持 Next16/React19 + Base UI/shadcn/Tailwind 彩色Shell；不复制商业模板，不因 M1 安装第二 UI 框架。真实项目没有 schema 驱动表单框架时优先用现有组件实现准确交互，不要求购置付费模板。
