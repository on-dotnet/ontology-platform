# 本轮真实测试矩阵

产品唯一变更为 ExpressionReadView 文案；无后端/API/DTO/生成物/合同/锁依赖/Design Token修改。源码TSX SHA256=7348c1a9eb529007a9312e3dd6970fba31f05b5865349ae817148bd2bc2d15d0。精确命令、UTC、真实退出与schema2 timingStatus见 checks/*.json；源码提交后补 testedCommit 输入绑定。

|检查|结果|实际范围/证据|
|---|---|---|
|定向组件|31 PASS /0fail/0skip，exit0，768ms|component-first-raw-output.json；包含新增RELEASE/DRAFT真实React render正反两例|
|完整Web|270 PASS /0fail/0skip，22文件，exit0，1492ms|web-tests.json 及 web-tests-raw-output.json；覆盖HTML转义、权限/版本hash/source/预算既有用例|
|lint /生产build /typecheck|各exit0，2939/5270/1896ms|web-lint/web-build/web-typecheck；Node24.22.1、pnpm11.28.8离线锁恢复|
|实际AppHost构建|exit0，6963ms；0error/1已有ASPIRE010 warning|backend-build；SDK10.0.402；为真实浏览器准备，非后端测试替代|
|verify -SelfTest|exit0，393676ms|selftest.json 及 selftest-raw-output.json；工具fixture测试不等于产品验收，不将工具测试总数与Web相加|
|真实工作区Smoke/故障注入|11 PASS，3425ms|browser/workspace-smoke.json；canvas故障310ms按预期FAIL，恢复PASS|
|真实历史草稿UI|29项已通过后Release脚本路径超时，原整命令exit1|browser/result.json；真实先读修订1、API另存修订2，再UI请求revision1，策略v4/投影1与源hash保持|
|真实固定ReleaseUI补验1|18PASS/1断言FAIL+1异常记录，exit1|browser-release-audit-attempt/result.json；Release文案/读取通过，错误假定审计查询本身无写入|
|真实固定ReleaseUI补验最终|25PASS/0FAIL/0skip，浏览器2955ms，原始失败另存|browser-release-retest/result.json；真实OIDC/发布/固定对象读取/说明/源hash/Manifest未变/无新增业务写审计/两项跨厂403|
|后端原实测复用|Semantic296+6、Publishing78、Query49、Agent33，原均0fail/0skip|backend-reuse-binding.json；原testedCommit80adf475，输入ls-tree9c004ef5…未变；本轮NOT_RERUN|
|证据Schema早检/diff-check|exit0|初始schema2仅结构，不伪称初始产品已验；最终绑定另测|
|精确资源DryRun|8项WOULD_DELETE，旧8卷不变，exit0|resource-dryrun.json；Apply待独立Review/提交后执行|

不是一次浏览器全PASS：第一次完整历史草稿部分通过，Release入口路径由/releases纠正为/ontologies；第二次原始断言将审计读取的platform.audit.read误计新增业务写审计。只修测试，PlatformEndpoints.cs:272证实该动作既有；最终仅排除此动作并要求审计窗口未截断，其他新增动作均拒绝。原失败、原脚本和回执保留；不重复原638全业务组合。

真实Release是本任务按当前v4正式审批发布后，随后草稿另存而保持固定的Release；未虚称本轮真实创建v1/v2/v3 Release。该历史策略语义由冻结合同、RELEASE组件fixture及精确未变后端证据核实。原E0锁屏外接熄屏与93分钟结果复用，本轮仅AC策略及有界观察，无宿主代码变更。

CI/Windows/Intel/付费模型/生产 NOT_RUN；Monaco BLOCKED；imports联网加载/OWL推理不在授权。没有新依赖。Agent思考/活跃/人工等待 UNKNOWN。原始G3-M5 ZIP不修改。

原始stdout逐字节保存于checks/*-raw-output.json的rawText（UTF-8重编码散列校验），避免终端输出的尾空行违反源码文本门禁。原.log仍在ignored artifacts，不改原始字节。首次最终静态检查因复制原.log尾空行exit1，已保留final-static-raw-output.json，改证据封装后精准复验。
