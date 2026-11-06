# Run38 取消互锁最小两文件补丁：精确批准申请

状态：候选已验证、独立Review PASS，尚未应用到产品。当前T38：aac57224cb27fe2f35dfd39a0d7b3b84e2a652ee。

真实完整I07最后取消场景失败。两个故障协调握手均ACK，此后没有取消POST；报告沿用query_handshake阶段名，不解释为握手失败。源码与2个实际组件RED证实：job URL变化重新读history，history执行源IO，新增readOwners使已有RUNNING任务的取消按钮也受阻。原失败的全部具体网络时序未捕获，不倒推补造。

候选仅修改已申请过的两路径：apps/web/src/features/connections/catalog.tsx、connections.test.ts。只允许已呈现且当前授权代际的任务Cancel越过未完成读取；Discover、普通重放仍等待读取。保留父操作锁、准确操作owner、撤权/revalidation与迟到响应保护；renderedGeneration防止旧处理器跨源403重验代际。无后端、合同、依赖、锁文件、迁移或浏览器等待时长变化。

精确补丁 SHA-256：c07539a54965042b584adc0220dec17dfe78e57046019121234727b1ab2619fe。

候选 catalog SHA-256：3e5c809bce499dea78f5a3fcbce44900f5719b08ed7005d0fd46324b1391b9ac。
候选 tests SHA-256：596670c6c929aa24c5b1a82c013129c058f7bb84def78321de2cefa661d4ca2a。

验证：现行组件2RED（取消disabled）；隔离候选完整23文件388测试PASS；类型/lint零错误。非作者argv_review独立核对实际加载路径、日志散列及取消/撤权/父锁保护后PASS。该结果不是新稳定构建/真实浏览器最终PASS。

如批准：现有任务分支应用此精确补丁，Web四项、真实取消及完整I07；初读403竞态及必要HTTP兼容烟测保留。T37不受影响后端继续按已批准影响政策复用，不重跑Nuget恢复、全部SelfTest或I02–I06。保留T38失败、恢复映射及所有原始记录，15MiB硬上限，不更新main、不进入M2。

再次申请的依据：Run37 PRODUCT-P1-SCOPE-REQUEST.md请求的是SHA 4a973548...的“上述精确补丁”，该已批准补丁已应用并验收。当前新增修正SHA不同，不能把旧两路径批准扩成任意后续产品修改。候选、测试和审查均已完成，批准仅为实际应用的最后一步。
