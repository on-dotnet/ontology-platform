# 最终全分支独立初审

Reviewer g2_whole_review（Astra/high），固定6154ebb3703031a49cf0c555c9f0c3596e3b7726..84193cfc83297f254b64e5462379291afbb7a83a；Spec/Quality FAIL，C0/I2/M2。

1. I1 OntologyService.SaveCoreAsync未更新SaveDraftRequest.Name，UI成功保存后清dirty丢新名称。要求实际PG响应/重读/目录、旧revision/审计失败不改名、幂等/边界验证。
2. I2 PublishingEndpoints六路由缺RequireAuthorization，三个typed POST在guard前绑定，匿名/错角色畸形正文绕过前置401/403及拒绝审计；未发现合法请求可直接越权发布。要求真实生产路由/PG拒绝审计与失败关闭控制。
3. M1 OpenAPI缺五个实际revision入口的必需强If-Match，发布审核/激活只有200无实际错误。要求真实导出/同步快照。
4. M2 当前运行OpenAPI实际生成97类而提交TS79，现有业务类型一致但完整产物不能精确复现。要求真实再生和重复零diff门禁。

四项全部接受，由一个g2_final_fix独立树统一finalfixwave，具体临时所有权/准确验收冻结于本轮final任务卡。不以未运行cold/CI/ZIP补齐主张。SEM原有无样例夹具前提的两个测试失败已另补显式NOT_RUN，同源码仍真实67/67，最终fixwave复核包含这条测试delta。
