# G4当前能力与规划入口

当前 main 为 `5168f2c93ca226caa521a6dc4ac85439335274c4`。2026-11-19，Doris review-fix-02 经 ChatGPT ACCEPT / GO，RF-02 关闭，已精确集成并回读。[Doris 验收与历史恢复](../tasks/G4-DORIS-MAPPING-QUERY-001.md)。当前[Oracle 任务](../tasks/G4-ORACLE-MAPPING-QUERY-001.md)已实测正式取消晚于固定 SQL 的 EOF，S0 与 AC03-B 保持 BLOCKED。任务分支 product-resume-01 已取得 AC03-A/C、S1 和双表 access 的限定资格。本轮在原工作树修正当前查询与审核身份并完成定向回归。S2 为 PARTIAL，在途 ABA 尚缺实机证据。当前 prepare 的资源峰值未获准入，S3 为 NOT_RUN。G4 总体 **PARTIAL**。[S2/S3 当前交付](../evidence/G4-ORACLE-MAPPING-QUERY-001/product-resume-01/s2-s3-01/report.md)

## 已合并能力与缺口

| 来源/阶段 | 已合并实现与历史验收范围 | 当前未完成范围 |
|---|---|---|
| M1 PG | 连接/TLS/只读探测/目录/权限及UI；见[M1任务](../tasks/G4-M1-CONNECTION-001.md) | 生产、未实测平台 |
| M2 Web | API_KEY_REF、HTTPS GET、Pagination=NONE连接/目录；见[Web任务](../tasks/G4-M2-WEB-01.md) | NONE/OAuth/其他分页、Mapping/Query |
| Doris M2 与限定 Mapping/Query | 本机 FE/BE、TLS/目录；单源双表、固定三能力与指定取消计划已集成，见[Doris 任务](../tasks/G4-DORIS-MAPPING-QUERY-001.md) | 跨源、其他计划与生产 |
| M2 Oracle | 本机ARM64 Free/TCPS连接/目录/API/UI；见[Oracle任务](../tasks/G4-M2-ORACLE-01.md) | Mapping/Query 已有条件准入，产品 AC 尚待当期实测；其他 edition/RU、整库灾备/生产 |
| M2 TDengine | WAIT_FOR_EXTERNAL_INPUT；该源任务未并入当前基线 | 本轮不恢复 |
| M3 Mapping | 单PG连接、≤2显式TABLE、每表≤12字段/≤100合成行、有限numeric、异人审核/发布/激活/回滚；见[M3任务](../tasks/G4-M3-MAPPING-001.md) | Doris 限定双表另见当前集成；其他来源、跨源/自由表达式 |
| M4 Query | 单PG三受控G4能力、固定5秒、六态/UI/MCP/canonical恢复、numeric/ABA；见[M4任务](../tasks/G4-M4-QUERY-001.md) | 三独立源失败组合、cursor分页、跨源、生产 |
| M5已合并 | 既有PG纵向组合＋工程入口收敛；工程Head606ca；整集-9/TIMEOUT保留，134唯一用例并集覆盖 | Doris 已限定集成；Oracle 与 Web 业务读取、Ontop 对比、五源/双架构仍未完成；旧产品资格不冒充本次FRESH |

当前实际平台为Mac ARM64及Linux ARM64合成容器；Windows/AMD64、CI未运行项和真实模型/生产保持NOT_RUN。AI OFF；合成IdP直接禁用传播限制继续单列。

## 冻结合同与历史恢复

原M5及S-01..S-70定义见[原阶段验收](../evidence/G4-00-CONTRACT-001/input-v1.1/docs/08-STAGES-ACCEPTANCE.md)。M3/M4经明确批准的限定范围分别见[Mapping合同](../evidence/G4-M3-MAPPING-001/contract-admission-request.md)与[Query合同](../evidence/G4-M4-QUERY-001/contract-admission-request.md)及各任务批准原件。

G4-00原设计/Schema/原批准字节不改。旧规划的PROPOSED、M1尚待批准及ADR阻断属于当时事实，按[历史索引](../evidence/G4-M5-INTEGRATION-001/history-index.json)从固定Base恢复；不据这些历史状态否定后续已批准实施，也不把未知条目升级PASS。

G5/G7仍依赖完整G4；G6独立支线不默认集成。当前授权和唯一状态仅由[授权入口](../tasks/current-authorization.md)及当前任务卡维护。
