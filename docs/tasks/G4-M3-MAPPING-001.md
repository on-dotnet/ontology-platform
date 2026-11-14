# G4-M3-MAPPING-001｜PostgreSQL 首条映射实施

唯一任务状态：**IMPLEMENTING / T5_REAL_RUNTIME**（2026-11-14）。用户已批准A–F中的PG首条完整映射路径实施；不扩大M4/其他源。

- 授权：本会话已批准A–F的PG首条完整路径实施及Web缓存TaskId最小补充；M2总体PARTIAL、TDengine WAIT_FOR_EXTERNAL_INPUT保持，其他源不推定等价。[A–F申请](../evidence/G4-M3-MAPPING-001/contract-admission-request.md)是唯一详细材料。
- Base：fetch后main/origin/main均e07eab20feb3fdef9e24a20dec12d11b15bd7d46；原main六个未跟踪.DS_Store保留。分支codex/g4-m3-mapping-001；树/Users/chasen/.codex/worktrees/g4-m3-mapping-001/ontology-platform；operationId=762e7b11-226a-45ca-9e7e-c686d57facc8，P0 RunId=p0-contract-20261114；当前RunId=mapping-impl-01。
- Owner：Master唯一作者，非作者只读Reviewer=/root/mapping_p0_review。owned_paths为A–F §F1准确实施清单及本任务三份文档（授权索引只追加）。read_only_dependencies：工程政策/PLANS/冻结架构、G3/G4合同、Contracts/Connections/Governance/Publishing/Ontology/Host/Web及测试。公共合同Single Writer仍Master，公共修改由Master唯一执行。
- 依赖缺口：PG仅探测/目录，无业务行验证；Mapping API/存储不存在；RM-02双分支缺失；现有事务审计可复用但无mapping action；当前Task消费者缺失，产品执行BLOCKED。
- 推荐：Connections拥有Mapping/Outbox，Governance独占审计/授权；固定G3只读、七项实证、PG不可变Release、异人/CAS和页面恢复。A–F包含合同差异、正反例、待批文件/资源。
- P0历史验证/Review：专项文档检查通过（7个JSON/2份绑定hash/13个负例定义），独立Review三项修正后定向复核通过；仓库静态verify.ps1因缺yaml解析器exit1保留，未安装；产品/build/服务/prepare/restore/CI/跨平台全部NOT_RUN。
- 实施验证（分阶段，不外推全链）：零下载prepare完成；真实持久化4/4（不可变约束、共同回滚、组织锁等待、幂等域、Outbox顺序/重复及跨实例容量）、真实源4/4、纯语义14/14；UI11/11、typecheck/lint和生产构建通过。Host/OpenAPI/TS与七页面已实现。独立Review发现源不可验证清屏、跨实例容量及回滚依赖最新草稿三项，已修并在验证。新合成realm实际OIDC、G3正式发布和PG目录已通过；真实UI发布/第二发布/回滚111检查、源撤权与audit/outbox/CAS回滚79检查、规则候选与冲突恢复35检查已分阶段通过；最终当前输入全覆盖与独立Review仍未完成。
- 资源：分支/树及新建本任务编译缓存KEEP，用于同会话后续实施；解除条件为获准收尾且成果安全集成/归档；本任务平台/源PG、Keycloak、Fuseki、RustFS、API六容器及宿主Web运行中；容器配额5.75GiB/7CPU，新合成凭据/TLS在私有ignored目录；新容器5ec1ae82b66ec932762596820291675621d81fbdccd4f3d9962ff215d70a56e3，卷ontology-g4-m3-mapping-impl-01_platform-data；完整资源ID/旧重建后验见任务artifacts。无下载/ZIP/旧KEEP清理。
- 下一动作：执行A–F末尾T0–T6计划，按影响验证与独立Review后停审查；不更新main、不恢复TDengine、不进M4。本轮已获批，继续同会话/分支/树；用户已确认接电和防自动睡眠。最终Head从Git回执取得，避免文档自引用。
