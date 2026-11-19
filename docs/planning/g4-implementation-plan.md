# G4当前能力与规划入口

当前主线：`606ca2d2c61964e6498dd72d5e9ad960d3593bf7`，2026-11-17已精确合并工程增量并回读；G4总体 **PARTIAL**。Doris Mapping/Query 的 S0–S3 已在任务分支完成既有实测；RF-01 与 E1–E3 已完成本地定向实测，分支仍待复审，见[当前任务卡](../tasks/G4-DORIS-MAPPING-QUERY-001.md)；不表示五源/全冶金流程/双架构完成。

## 已合并能力与缺口

| 来源/阶段 | 已合并实现与历史验收范围 | 当前未完成范围 |
|---|---|---|
| M1 PG | 连接/TLS/只读探测/目录/权限及UI；见[M1任务](../tasks/G4-M1-CONNECTION-001.md) | 生产、未实测平台 |
| M2 Web | API_KEY_REF、HTTPS GET、Pagination=NONE连接/目录；见[Web任务](../tasks/G4-M2-WEB-01.md) | NONE/OAuth/其他分页、Mapping/Query |
| M2 Doris | 本机合成FE/BE、TLS连接/目录/生命周期；见[Doris任务](../tasks/G4-M2-DORIS-01.md) | Mapping/Query、生产 |
| M2 Oracle | 本机ARM64 Free/TCPS连接/目录/API/UI；见[Oracle任务](../tasks/G4-M2-ORACLE-01.md) | Mapping/Query、其他edition/RU、整库灾备/生产 |
| M2 TDengine | WAIT_FOR_EXTERNAL_INPUT；该源任务未并入当前基线 | 本轮不恢复 |
| M3 Mapping | 单PG连接、≤2显式TABLE、每表≤12字段/≤100合成行、有限numeric、异人审核/发布/激活/回滚；见[M3任务](../tasks/G4-M3-MAPPING-001.md) | 非PG/跨源/自由表达式 |
| M4 Query | 单PG三受控G4能力、固定5秒、六态/UI/MCP/canonical恢复、numeric/ABA；见[M4任务](../tasks/G4-M4-QUERY-001.md) | 三独立源失败组合、cursor分页、跨源、生产 |
| M5已合并 | 既有PG纵向组合＋工程入口收敛；工程Head606ca；整集-9/TIMEOUT保留，134唯一用例并集覆盖 | 非PG映射查询、五源/双架构仍未完成；旧产品资格不冒充本次FRESH |

当前实际平台为Mac ARM64及Linux ARM64合成容器；Windows/AMD64、CI未运行项和真实模型/生产保持NOT_RUN。AI OFF；合成IdP直接禁用传播限制继续单列。

## 冻结合同与历史恢复

原M5及S-01..S-70定义见[原阶段验收](../evidence/G4-00-CONTRACT-001/input-v1.1/docs/08-STAGES-ACCEPTANCE.md)。M3/M4经明确批准的限定范围分别见[Mapping合同](../evidence/G4-M3-MAPPING-001/contract-admission-request.md)与[Query合同](../evidence/G4-M4-QUERY-001/contract-admission-request.md)及各任务批准原件。

G4-00原设计/Schema/原批准字节不改。旧规划的PROPOSED、M1尚待批准及ADR阻断属于当时事实，按[历史索引](../evidence/G4-M5-INTEGRATION-001/history-index.json)从固定Base恢复；不据这些历史状态否定后续已批准实施，也不把未知条目升级PASS。

G5/G7仍依赖完整G4；G6独立支线不默认集成。当前授权和唯一状态仅由[授权入口](../tasks/current-authorization.md)及当前任务卡维护。
