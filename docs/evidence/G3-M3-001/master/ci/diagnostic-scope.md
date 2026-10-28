# Canonical诊断运行范围

默认main workflow尚未包含workflow_dispatch，所以首次手动诊断不可触发。为真实逐层修复Linux归档兼容，只有精确`codex/g3-m3-master`分支push且Head提交说明含`[canonical-diagnostic]`时跳过engineering及应用层步骤，保留真实canonical restore/cold/export/save和失败记录。main、其它分支、PR或普通task提交始终完整运行；手动canonical_only只用于default集成后诊断。

这类运行明确打印product NOT_RUN、full required CI NOT_VERIFIED，不能满足双job成功的Review V3门禁或作为main集成/最终同Head CI。缓存仍只有可信push可save；手动传递仍严格workflow_dispatch，不自动触发arm64。

正反测试从实际workflow读取条件并验证事件/分支/marker及全部四个应用步骤同条件、cache push-only。RED2失败后GREEN5通过。真实新runner结果另存，不预填PASS。
