# G4-M3-MAPPING-001｜P0 合同审查

唯一任务状态：**P0_DESIGN_READY_FOR_REVIEW**（2026-11-14）。仅文档，产品实施尚未批准。

- 授权：本会话批准附件P0；M2总体PARTIAL、TDengine WAIT_FOR_EXTERNAL_INPUT下限定M3设计；PG完整映射路径为待批建议，其他源不推定等价。[A–F申请](../evidence/G4-M3-MAPPING-001/contract-admission-request.md)是唯一详细材料。
- Base：fetch后main/origin/main均e07eab20feb3fdef9e24a20dec12d11b15bd7d46；原main六个未跟踪.DS_Store保留。分支codex/g4-m3-mapping-001；树/Users/chasen/.codex/worktrees/g4-m3-mapping-001/ontology-platform；operationId=762e7b11-226a-45ca-9e7e-c686d57facc8，RunId=p0-contract-20261114。
- Owner：Master唯一作者，非作者只读Reviewer=/root/mapping_p0_review。owned_paths仅本卡、docs/evidence/G4-M3-MAPPING-001/contract-admission-request.md、docs/tasks/current-authorization.md（只追加）。read_only_dependencies：工程政策/PLANS/冻结架构、G3/G4合同、Contracts/Connections/Governance/Publishing/Ontology/Host/Web及测试。公共合同Single Writer仍Master，本轮不修改正式合同。
- 依赖缺口：PG仅探测/目录，无业务行验证；Mapping API/存储不存在；RM-02双分支缺失；现有事务审计可复用但无mapping action；当前Task消费者缺失，产品执行BLOCKED。
- 推荐：Connections拥有Mapping/Outbox，Governance独占审计/授权；固定G3只读、七项实证、PG不可变Release、异人/CAS和页面恢复。A–F包含合同差异、正反例、待批文件/资源。
- 验证/Review：专项文档检查通过（7个JSON/2份绑定hash/13个负例定义），独立Review三项修正后定向复核通过；仓库静态verify.ps1因缺yaml解析器exit1保留，未安装；产品/build/服务/prepare/restore/CI/跨平台全部NOT_RUN。
- 资源：仅分支/树KEEP，用于同会话后续实施；解除条件为获准收尾且成果安全集成/归档；无服务/证书/下载/ZIP，无旧KEEP清理。
- 下一动作：文档Review已完成，普通提交/push交付后停准入；不更新main、不恢复TDengine、不进M4。获批后同会话/分支/树继续。最终Head从Git回执取得，避免文档自引用。
