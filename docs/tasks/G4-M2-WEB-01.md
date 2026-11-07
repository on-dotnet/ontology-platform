# G4-M2-WEB-01｜一页实施清单与唯一状态

状态：**P0_BLOCKED / 等待边界裁决**；未实施产品代码，不是 READY_FOR_CHATGPT_REVIEW。
授权：2026-11-07 用户明确批准附件单 Web HTTPS GET；[附件](../evidence/G4-M2-WEB-01/authorization.md)。
Base：`b3b68500d76ab5965fcc540afb883ca605cb15dd`，真实 fetch 一致；分支 `codex/g4-m2-web-01`。
Worktree：`/Users/chasen/.codex/worktrees/g4-m2-web-01/ontology-platform`；Master 单写，p0_review 非作者只读。

## 清单

- [x] P0：核实基线/独立树、DTO/SPI/16路由、宿主资源、既有环境入口、官方 .NET HTTP API；详情见[P0](../evidence/G4-M2-WEB-01/p0.md)。
- [ ] P0闭合：Web认证合同裁决；离线Web缓存来源核验与两次幂等prepare；TaskId消费者准入；TLS/socket平台见证。
- [ ] 公共分发：准确文件冻结后编写PG/Web正反合同测试→非作者Review→最小typed dispatcher；PG不变，其他三类型继续拒绝。
- [ ] Web：可信精确operation/HostPolicy注册→DNS全地址与socket绑定→正常TLS→固定GET/认证→有界目录/取消/生命周期。
- [ ] 验收：先真实OIDC/API/HTTPS/UI烟测；再workflow plan/verify按影响执行安全负例、权限/SecretRef、PG回归、取消见证及浏览器闭环。
- [ ] 产品交付：独立Review→提交/输入绑定→唯一V3→独立重开→回执；不更新main。

## 所有权与依赖

当前实际 owned_paths：本任务卡、`docs/tasks/current-authorization.md`追加段、`docs/evidence/G4-M2-WEB-01/**`。产品写入尚未开启；不得把目录上限当冻结的准确文件清单。
只读依赖：Contracts/G4ConnectionModels.cs、G4ConnectionRules.cs；Connections 的 Abstractions/Application/Persistence/Adapters；Api/G4；现有Web Connections；workflow*、门禁登记、冻结架构和当前工程政策。
后续准确产品owned_paths必须在合同裁决后冻结于本卡；共享配置由Master单写。无新增依赖/下载/费用、无新DB语义/公开wire/权限；Oracle/Doris/TDengine及M3/G6不在范围。

## 恢复与停止

只在[P0决策](../evidence/G4-M2-WEB-01/decision.md)获得所需明确授权后解锁相关实现；普通修复无需逐补丁审批。现有prepare失败不重复整链。保留当前离线缓存和原始运行日志，任务未关闭；不清旧任务资源。
本轮仅形成P0阻断见证与非作者审查，不能称Web完成。后续最终产品ZIP必须在真实验收完成后另行形成。
