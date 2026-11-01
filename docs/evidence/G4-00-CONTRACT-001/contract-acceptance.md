# G4-00 设计验收与裁决索引

全部产品S-01..70 NOT_RUN。此表仅文档/静态设计范围；最终命令/独立Review以static-results、review-cases-results及review-receipt为准。

| C | 本轮证据与限制 |
|---|---|
| 01 | source-binding + check-bindings保持G2/G3全部引用源hash；不改本体 |
| 02 | connections五源表+输入04详细矩阵；高级字段限制以Schema为上限 |
| 03 | server Actor/完整scope交集，T01/02书面威胁推演 |
| 04 | 三层只读与typed plan/SSRF；产品安全NOT_RUN |
| 05 | mapping稳定版本/hash；canonical正式字节需M3另冻 |
| 06 | 独立审批/CAS/Outbox/失败不切active；ROLLBACK DTO子集局限RM-02 |
| 07 | 六态/证据链/时间保留；完整Datum局限RQ-02 |
| 08 | OFF规则+人工可完成设计路径；实际界面NOT_RUN |
| 09 | 仅静态本机，无模型/外部源/生产连接 |
| 10 | 不创建Docker；后续双架构/精确资源条件已记录 |
| 11 | M1→M2→M3→M4→M5，G5/G7依赖，计划明确 |
| 12 | 原包唯一09合同/执行批准历史留存；本会话新增明确批准 |
| 13 | 全部新增API/DTO/权限/码PROPOSED，源码零改 |
| 14 | G6支线未合main，不将Docling阻断转给G4 |
| 15 | 既有唯一生成链不改，设计Schema不生成产品模型 |
| 16 | 13单元/恢复/API映射纳入UI合同；不称已实现；RQ-01补实体选择 |
| 17 | 原21正/16Schema负/3语义负/2内联实测；G2十一字段+候选七字段严格对照 |
| 18 | create仅config/secretRef/command等五字段，expectedRevision=0；原R06..08 |
| 19 | TD无重复ref，NONE必须null/认证非空；原R09..12 |
| 20 | U07/U09/U10/U11读链齐备；RM-01修复状态分层；回滚DTO实施仍锁 |

## 审查裁决与原始失败

RC-01：原Schema不能表达同SITE_A/externalId001的选定IRI。RQ-01增受控entityIri，定向schema/当前scope/候选/版本模型反例通过；只设计，不代API。
RC-02：NEEDS_DECISION/PROPOSAL_READY是工作流标签，Draft wire使用NEEDS_REVIEW/READY_FOR_PROPOSAL；RM-01明确分层并验证原标签被拒/合法枚举接受。
RQ-02/RM-02：原输入分别缺完整Datum/回滚载荷，归档为M4/M3实施前必须另冻的机器合同，不改旧DTO、不伪造通过。
RQ-03：未登录或无资产权限只ProblemDetails，不读取/构造含敏感ID的snapshot；合成admission例验证设计顺序，不证明运行安全。

## G2对照

check-bindings实读g2-models.json及生成C#：SemanticQueryResult 11字段、EntityCandidate 7字段、CommandContext 4字段/创建0；所有对应生成record Disallow；旧路由Produces<SemanticQueryResult>保持。G4嵌套Evidence/Snapshot/SubSource明确不兼容，不做强制投射。精确字段列表及文件SHA见static-results/source-binding。没有编译/HTTP/反序列化运行的G2产品兼容复验，状态NOT_RUN；可观察结论限字段和源字节未改。
