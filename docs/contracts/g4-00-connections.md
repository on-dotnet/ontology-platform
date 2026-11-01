状态：PROPOSED_G4_CONTRACT / NOT_IMPLEMENTED。TaskId：G4-00-CONTRACT-001；Master 单写。基线 d1a61daffe844475b07705797e3ad325cc3f2945。

本文件为 V1.1 输入的仓库合同入口。下列引用章节按原字节归档，属于本合同的详细定义；当前裁决优先于输入中的建议，G2/G3 冻结合同优先于 G4。输入包历史“未授权”描述保留，2026-11-01 用户明确批准本任务仅合同归档、验证、独立 Review；不是产品实施许可。

## 五源与配置

完整字段、探测及方言矩阵见[五源定义](../evidence/G4-00-CONTRACT-001/input-v1.1/docs/04-CONNECTOR-MATRIX.md)，唯一请求及候选 API 见[API 合同](../evidence/G4-00-CONTRACT-001/input-v1.1/docs/05-DATA-API-CONTRACT.md)。安全约束见[SQL 与网络边界](../evidence/G4-00-CONTRACT-001/input-v1.1/docs/06-SECURITY-AND-QUERY.md)。这些是拟议合同，不是已部署端点或已批准驱动。

| 类型 | 配置边界 | 发现与不可丢失信息 | 停机条件 |
|---|---|---|---|
| POSTGRESQL | host/port/database/username/sslMode/allowedSchemas；值参数化，标识符来自固定目录 | 可见列、精度、array/jsonb、时间类型 | search_path 越权、只读证明缺失、TLS不可信 |
| ORACLE | 首期 host/port/serviceName/username/tls/allowedOwners；不接收任意描述符 | owner/quoted identifiers/NUMBER/DATE/TIMESTAMP/CLOB | 未批驱动/许可、alias 或 Wallet 功能未冻结、时间精度不明 |
| DORIS | FE host/port/catalog/database/username/tls | MySQL wire 不等于 MySQL 语义；独立类型/分页能力 | FE身份未验、DECIMAL或时区不确定 |
| TDENGINE | 受控 WS endpoint/database/timezone/precision；唯一顶层 secretRef | stable/subtable/tags/ms-us-ns | native/REST fallback未批、精度损失、WS权限不明 |
| WEB_API | 已批准 origin/GET operation/参数及分页模板 | JSON missing/null/number与schema/游标 | SSRF、远端ref、重定向或OAuth目标未批 |

ConnectionCreateRequest 仅 displayName、scopeSelection、config:{type,profile}、secretRef、command。测试包装 schemaKind/payload 不进入 REST body。command.expectedRevision=0；编辑必须正修订+同值 If-Match。TD profile 不得有 credentialRef。匿名 Web API NONE 必须 secretRef=null，其余认证必需非空引用。SecretRef 本身不授予访问，服务器验证组织、主体、用途、有效期及 SecretVersion；读响应不得泄露秘密。

源端最小权限、确定性计划编译、Adapter 参数化/预算三层共同构成只读；SELECT 前缀不够。禁止多语句、CTE写、函数副作用、管理接口、自由对象名；本轮不连任何源。URL/DNS/IP/实际socket绑定、TLS/SNI、redirect/next/OAuth/proxy各跳同样授权；生产私网仅准确网络策略例外，不泛放网段。

## 状态及权限

持久管理状态 DRAFT/ACTIVE/DISABLED；TESTING/TEST_OK/TEST_FAILED、DEGRADED/ROTATING_SECRET 是探测或健康状态，不允许 UI 图混作同一数据库枚举。输入 UX 的 DRAFT→TESTING→TEST_OK→ACTIVE 表示组合工作流。创建仅 DRAFT，测试成功不自动启用；明确 enable 命令重新授权和核验 configHash、secretVersion、schemaScope、有效期。配置/凭据变化使旧测试失效。停用拒绝新调度，取消在途任务并保存真实终态。失败不能自动恢复 ACTIVE。

connection.read/manage/test/secret.manage、schema.read/discover 均 PROPOSED；默认不因角色存在就授予新增权限。Actor 从既有 OIDC 可信身份取得，scopeSelection 是资源选择且必须完整子集；不当成 ActorScope。源数据读取仍额外满足 source/field ACL，运维或管理权限不自动包含业务读权限。

## 未决边界

输入 UI 的 Oracle alias/SID/Wallet、PG CA/pool、Web headers 等高级字段超出 V1.1 严格创建 Schema。裁决 CLARIFY_IN_G4_CONTRACT：首期仅 Schema 接受字段，额外能力以未来 ADR/版本化 DTO 审批后开放，不能向现有请求偷加字段。输入的厂商版本、退场日期及许可为上游来源声明，本轮未重新核验，不提升为 OFFICIAL_DOC_VERIFIED。真实安装/镜像/平台/TLS全部 NOT_RUN。
