# V3 命令行长度修复：变更 A 授权

用户于本会话 2026-11-06（Asia/Shanghai）明确说：

> 变更A 同意，变更B的根因是什么？为什么这么大 ？不都是任务要求必须的资料吧？

仅批准已审提案变更 A。提案SHA256：8f2e89a223a569d0ef866b9c2ecb6c26a8919d7ef63532a3c2abdab01cc5494d。

TaskId=G4-M1-MAIN-INTEGRATION-001；Base=d1a61daffe844475b07705797e3ad325cc3f2945；候选必须以03ce658c04fc810e7a10dc14eea1d64124ddbf12为祖先。仅V3、可信批准原文blob散列一致的创建与VerifyOnly可使用有界等价pathspec。完整argv至多256项；Unix UTF-8含NUL至多8192字节；Windows无法可靠确认实际渲染时拒绝fallback。真实启动仍失败则保留并停止。保留原始blob分类、双侧安全扫描、完整文本diff与创建/重开一致性；补集路径集合须精确相等，重叠或两种向量均超限拒绝。V1/V2及无本批准的历史V3保持原行为。

Master唯一作者；可修改docs/development/review-package-spec.md、scripts/create-review-package.ps1、scripts/tests/ReviewPackage.Tests.ps1及本任务说明/证据。先正反测试及独立Review，提交后绑定新输入；不把Run34产品结果伪装为新T执行。

变更B未批准：不实施64MiB例外，15MiB硬限制保持。仅调查体积根因及可审的减量方案，不删原证据、不改历史、不自动改变证据选择或diff合同。不更新main、不进入M2。
