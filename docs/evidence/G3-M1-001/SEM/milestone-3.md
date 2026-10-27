# SEM Milestone 3 — Backend implementation complete / review pending

仅M1后端。本checkpoint新fresh真实PG/Jena/RustFS：SemanticTests 89/89、PublishingTests 53/53，0跳过。比较包含四源累计5s、解析中取消、128/129 blank边界、近似非同构和对称非同构100000搜索节点耗尽（固定search_node_budget）。评估包含报告/assessment/命令/审计原子回滚、同命令重放、角色/完整scope、过期/伪造/跨profile/旧报告拒绝。四源BOM/CRLF/no-op与固定历史revision比较均实际运行。

迁移由Master独占：f1cd505（Up模型）、b48a68a（forward-only Down）。真实Down缺陷首轮导致assessment表先被删除，已保留原失败；修复后持锁/无锁两次均NotSupportedException，报告/assessment/源/AppliedMigration全保持。Initial-only独立子库保留原55P03/P0001精确负例并实际通过。ontology.assess事件由Master31b5ff5登记后真实审计通过。

V1使用独立原G2支持清单与原Binding字段顺序；新发布只能携带服务端持久Semantics并写V2。真实V1对象/图/PG夹具验证旧读、回滚正反、新V2共存、当前草稿推进及assessment过期不影响V1回滚。只公开合成manifest输出位于/private/tmp/g3-sem-manifests，供Master保留兼容二进制读回。

Query/Agent新fresh回归仍在执行；Query首轮48/49，缺来源测试以未声明unknownRecord代替删除字段而被新精确策略阻断，已改为真正删除唯一sourceRecordId字段，待复跑。SelfTest首轮缺项目PyYAML而FAIL；仅/tmp按已批准requirements精确hash恢复后执行中。未把未完成项当作PASS。Master组合Host/OpenAPI、独立Astra审查及同Head CI仍NOT_RUN/NOT_VERIFIED，不具备自行main集成资格。
