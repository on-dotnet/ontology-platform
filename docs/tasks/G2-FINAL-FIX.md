# G2 最终全分支统一修复波

来源：独立Astra whole-review固定6154ebb..84193cf，C0/I2/M2。完整初审见本轮master/whole-review-initial.md。按最终Review流程只派一个统一fix Owner `g2_final_fix`，Reviewer保持`g2_whole_review`。独立托管树`/Users/chasen/.codex/worktrees/g2-final-fix/ontology-platform`，分支`codex/G2-FINAL-FIX`，Base `96db23bb17627cfa37efbba113c1641906b931d1`（841+SEM测试夹具前提b16c628）。不扩大G2/依赖/费用/系统权限。

临时single-writer明确移交：OntologyService.cs及DraftRevisionTests.cs；Api/G2/PublishingEndpoints.cs、G2OpenApi.cs及SecurityTests新的发布前置授权/运行OpenAPI测试；g2-generated.ts由工具生成、generate-types.mjs及对应现有/新增生成测试，package.json只准必要脚本无依赖；实际g2-platform.openapi快照；g2-live-browser及极小跨平台g2-trace-browser路径边界修正；master/final-fix-*及报告。Master停止写这些路径，其他模块/锁/CI/迁移/DTO机器模型只读。完整目录均以各自任务同路径解析，不跨树抢写，不派嵌套Agent。

统一四项：真实保存新Name且CAS/事务审计/幂等/边界保留；六个发布路由在typed绑定前施加正确角色策略并有PG拒绝审计/失败关闭；真实OpenAPI声明五个强If-Match入口及实际错误；全runtime TS产物精确再生/重复零diff。附Root路径边界小修使用平台标准分隔符，拒跨根/驱动，不宣称Windows实跑。

必要夹具补齐已获Master批准：PUB RollbackBoundaryTests/PublicationFaultTests/PublishingFlowTests、QRY QueryFaultTests仅相应SaveDraftRequest补Name=draft.Name，不改原断言。实际更正为PUB5+QRY1共6处，最初消息“7”计数更正。更新输入使原CAS/故障测试继续进入真实路径，禁止放宽名称规则。原SEM67/真实PUB50/QRY49/AI33仍需零skip真实验证，增加Name用例按实际新数记录。

SEM b16c628此前测试-onlydelta：无样例环境时2pure PASS/65NOT_RUN；配置错误仍FAIL，同源码真实PG/Jena67/67，不把skip算产品通过。最终fixwave限定复审包含此delta。

要求覆盖测试先真实RED再GREEN，保留命令/退出/原始safe输出/SourceHash；全量现有门禁不删减。C#准确中文XML及局部用途注释，复杂TS中文JSDoc。完成后Owner commit/push DRAFT/PARTIAL，Master重跑真实OIDC+新Name+Malformed发布负例、完整冷启动六门、Linux两job，给原Reviewer一次完整fix-range复核，才main集成/最终ZIP。只读审查不是实际环境结果，未知不可升级PASS。


## Master集成回执（2026-10-26）

本卡对应源码/已批准模块范围已独立复审并纳入Master真实整体验收；实际命令/计数与原始失败保留于本轮master/validation.json、delivery-report.md及模块报告，不把原DRAFT提交推送等同已通过。首次main快进推送b1ff0a68915c272846038af96a00da3acbb95538；最终文档Head/CI/唯一ZIP按封包manifest和独立回执确认。总体PARTIAL，Monaco按人类暂停/真实模型与跨平台生产未运行等例外不变；本轮交付后等复审，不扩展下游。
