# Canonical诊断运行范围

默认main workflow尚未包含workflow_dispatch，所以首次手动诊断不可触发。为真实逐层修复Linux归档兼容，只有精确`codex/g3-m3-master`分支push且Head提交说明含`[canonical-diagnostic]`时跳过engineering及应用层步骤，保留真实canonical restore/cold/export/save和失败记录。main、其它分支、PR或普通task提交始终完整运行；手动canonical_only只用于default集成后诊断。

这类运行明确打印product NOT_RUN、full required CI NOT_VERIFIED，不能满足双job成功的Review V3门禁或作为main集成/最终同Head CI。缓存仍只有可信push可save；手动传递仍严格workflow_dispatch，不自动触发arm64。

正反测试从实际workflow读取条件并验证事件/分支/marker及全部四个应用步骤同条件、cache push-only。RED2失败后GREEN5通过。真实新runner结果另存，不预填PASS。

## 大小写语义纠正

独立Review发现GitHub表达式字符串比较与contains忽略大小写，首版Python eval不能证明准确ref。现改为只读scope job调用ci_scope.py，使用Python准确大小写比较，只输出canonical_only boolean；engineering及4应用步骤共同消费同一输出。补大写同名分支/大写marker正反例，保留首版不足，不把测试fixture提升为真实runner事实。
