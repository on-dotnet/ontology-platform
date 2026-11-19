# G4-DORIS-MAPPING-QUERY-001｜Doris Mapping/Query

## 当前执行与授权

唯一执行状态为 **REVIEW_FIX_IN_PROGRESS**。ChatGPT 对 `0c287e45e1c355a00cfd5403d6cb787026b127e1` 的裁决为 REQUEST_CHANGES。RF-01 阻断 AC09。G4 总体 PARTIAL。分支 `codex/g4-doris-mapping-query-001`，主线 `606ca2d2c61964e6498dd72d5e9ad960d3593bf7`。实现与证据采用同一 TaskId，本次 EvidenceRunId 为 `review-fix-01`。资源 Owner 仍为 `implementation-01`。

Master 单写。范围、所有权、数据与期限以[唯一 A–F 合同](../evidence/G4-DORIS-MAPPING-QUERY-001/contract-admission-request.md)为准。当前复审修复覆盖共享语义期限、三个既有工程入口及对应定向验证。

## 原实施验收与本轮资格

下表全部记录 implementation-01 当次结果。AC06 固定 HEAP 的取消因果获接受。AC09 原测试未覆盖发布根清理。新候选的定向执行与资格见[复审证据](../evidence/G4-DORIS-MAPPING-QUERY-001/review-fix-01)。

| AC-ID | 行为与正反Given/When/Then（完整场景见规格E） | 实现/测试位置 | 最早验证层/结果 |
|---|---|---|---|
| AC01 | 已发布且完整授权则查询成功；错用途/未发布拒绝 | MappingValidationService/QueryBindingReader，DorisMappingQueryTests | 正式四角色单表及双表发布均已运行，正例通过 |
| AC02 | decimal同值异scale连边；不等/NULL不连 | DorisQueryReader/G4QueryTests | 独立 SQL 与整数系数参考、正式关系查询同得 T1/T2 |
| AC03 | 全集唯一身份可发布；身份碰撞/未知表模型拒绝 | DorisMappingSourceValidator | S0 模型拒绝，S1 不支持的身份拒绝，S2 多父和危险身份方案被拒 |
| AC04 | 当前授权有效可提交；撤权/轮换先提交无成功副作用 | G4QueryAuthorizationTests/G4QueryRaceTests | 源 SELECT 撤销、读后撤 execute、会话失效及在途轮换 1→2 均拒绝；新发布及历史字节已复核 |
| AC05 | 元数据兼容可用；列/模型变化旧批准拒绝 | QueryBindingReader/新Doris测试 | 审批后形状变化拒绝激活；同查询读行后到目录后验前真实改名返回 422，原 tablet、DDL 与行摘要恢复 |
| AC06 | 完成读取正常返回；取消/断开不得EMPTY或迟到成功 | G4QueryHttpTests/新Doris测试 | b676 独立逐任务证明通过，FE ≤34.371 ms、BE ≤64.521 ms，零成功副作用；124f 原裁决 NO-GO |
| AC07 | 当前activation可提交；同query ABA拒绝 | G4QueryRaceTests | 两个真实同查询 ABA 时序均在原期限内以 409 拒绝，零成功副作用；拒绝当刻 RUNNING |
| AC08 | 新会话恢复原字节；撤权/到期拒绝且不业务重查 | G4QueryPersistenceTests | 新会话恢复原字节；撤权 403；一次性查询到期后结果/证据均 410，FE 审计业务查询集合未增加 |
| AC09 | 六态/可信前缀正确；超预算无COMPLETED | G4QueryTests/G4QueryWireTests | 空集、歧义、扇出、真实断开、超宽列及最终提交截止已测；实体 101 行查询只返回前 100 个可信候选，准确复原已复核 |
| AC10 | HTTP/UI/MCP相同结果；PG旧字节不变 | G4QueryMcpTests/既有Web测试 | PG 两组历史 manifest/result 与 standard assessment 通过。三项 UI 能力和四个 MCP 与 HTTP 原字节相同，撤权 403 清屏与身份切换通过 |
| AC11 | 分别读取记录真实窗口；不盖虚假snapshot | 新Doris测试 | S0 受控写入与 S1 UNKNOWN/null 已核验 |

## 验证、恢复与历史

- 原实施的 S0–S3、134 个唯一历史工程用例的准确口径、失败原件和当时的等待状态，可在 Git 对象 `0c287e45e1c355a00cfd5403d6cb787026b127e1:docs/tasks/G4-DORIS-MAPPING-QUERY-001.md` 与[原实施证据](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01)回读。
- 先核六项任务资源的准确 ID、镜像、卷、所有权、VM 配额、余量及当前构建。仅三项持久服务可恢复，定向验证后依次原生关库或 TERM。三个易失服务继续持卷运行。释放须另行集中裁决，详见[资源保全卡](../evidence/G4-DORIS-MAPPING-QUERY-001/review-fix-01/resource-retention.md)。
- prepare 失败保留原件。用既有 `execution_preflight.py run --cost short` 对同一原命令身份做有界定位，保存双流、退出码与看门狗状态。原身份恢复后方可继续。
- 当前关口为 ChatGPT 复审。生产、旧 M4/M5 KEEP、TDengine 与 G5 均在本批之外。
