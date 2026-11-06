# V3 本任务证据减量授权

用户于本会话 2026-11-06（Asia/Shanghai）在阅读体积根因及减量建议后明确说：

> 好的，那按照你的建议，先保持15M，请继续。

批准方向：保持15MiB硬限制；原始证据、失败记录、Git blob和恢复映射全部保留。包内保留最终完整验收、关键失败、修复审查、审批及恢复链；其余证据按准确提交、路径、blob OID、SHA256、字节数索引恢复。完整非证据源码/配置/合同/测试差异保留；纯证据文本变化以完整双侧变更索引代替重复的文本patch。创建与独立VerifyOnly使用同一可信规则，不实施64MiB容量例外。

仅适用V3、TaskId=G4-M1-MAIN-INTEGRATION-001、Base=d1a61daffe844475b07705797e3ad325cc3f2945、Head以9ed3b9283acc81805737fb19efd3123281010103为祖先且本批准原文blob散列准确。旧包和其他任务保持原规则；manifest字段不能自行授予权限。

Master唯一作者；允许修改docs/development/review-package-spec.md、scripts/create-review-package.ps1、scripts/tests/ReviewPackage.Tests.ps1及本任务说明/证据。先冻结具体选择/恢复合同和正反测试，独立Review，提交稳定输入，再完成适用完整本地验收和唯一V3独立重开。原Run34及历次失败保持真实历史，不替代新输入验收。

本授权不更新main，不进入M2，不允许下载、付费、全局清理、历史改写或丢弃原始证据。交付后停在READY_FOR_CHATGPT_MAIN_MERGE_APPROVAL。
