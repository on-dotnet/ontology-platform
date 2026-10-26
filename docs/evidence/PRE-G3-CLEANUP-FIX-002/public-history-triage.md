# C4 公开仓库历史与证据有限检查

GitHub实际visibility=PUBLIC，当前open PR=[]。扫描全可达commit/tree/blob/task refs及annotated tags（含嵌套tag），本地refs/codex辅助快照单独标注，不把它们等同已公开。私有工具/凭证路径仅metadata，ignored runtime/PFX/env不读取；不输出疑似值，不重写历史。原始报告exit2表示需要triage，不伪改成scanner本身PASS。

独立quality_reviewer public_history_review逐blob内存AST核验六项，全部not_actionable/high confidence：

- bootstrap-keycloak.py三版本26f1851/7fe73c7/b26ed89：admin_password变量来自环境引用；另一版client_secret/password为secrets.token_urlsafe随机生成表达式，Git中无这些值的字面凭证。没有读取环境值。
- verify-alloy-boundary.py三版本7c6ef90/99a2169/e005a16：Docker标准宿主别名拼接临时ThreadingHTTPServer端口，发送合成marker/log/span到测试Sink并验证marker不导出，不是私有生产地址。

独立补核当前Agent运行代码：仅Development+显式EnableDeterministicHarness启用离线工具；ApprovedModel provider_not_configured，持久化/执行端再次拒绝非deterministic。未见真实云key或实际外部模型配置。samples/g2五TTL使用W3C词汇/合成URN，明确人工合成与负例，不是已证明的真实业务数据。

原Important1：只扫commit树遗漏直接tree/blob refs及tag消息（本地实际存在6个辅助tree refs）。补真实RED→GREEN覆盖direct refs、tag和无独立ref的inner tag。原Important2：auxiliary COMMIT私有工具路径被误扫内容；补合成snapshot commit RED，现全局private_path metadata-only且nonaux reachable来源分开，独立复放内容命中0/metadata1/未输出marker。独立最终9/9测试PASS；C0/I0/M0，两个缺口关闭。扫描器SHA256=dab18f09113dbb3b49e349a7422ffe09827d4b85b36181a9fb8cdc7eda3a25c7，tests SHA256=a6da9d65d3fcf810bb0be8df769af161a4acc9c549aa97afb5d8c5e44d5bc1b5。

独立实际重扫在工具中间Head0a920f4：285commits/2194blobs/46128151 bytes、6原命中、0omission、13aux refs。后续新增纯治理提交需按真实Head重扫或明确scope，不把初始数量当最终数量。没有真实风险轮换建议；若后续发现真实值，只报位置/类别并提轮换/历史处置，不擅自改历史。

结论：PASS（限定有限扫描+人工triage），不等于全库语义隐私、任意混淆、未获取远端/不可达对象的安全认证；这些NOT_VERIFIED。readOnly字段不是OS沙箱。

## C3最新独立覆盖

public_history_review在b9322e599aabac6fac8ed8a6f4ceeae767d1323b独立重跑：289 commits、2235 unique blobs、46,825,908 bytes、原6项相同blob/path/category、unscanned0，C0/I0/M0，无新增候选。15本地Codex辅助refs不等于公开证据；原6项not_actionable/high结论保持。精确报告public-history-c3.json SHA256bddb20335b1a672fe117c95ba79836317494f0ac78ba3a7ecb2ec172cda553e9。扫描exit2表示需人工triage而非发现真实秘密；未重写历史。语义隐私/任意混淆/未获取远端对象仍NOT_VERIFIED。
