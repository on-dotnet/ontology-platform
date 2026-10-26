# G2-READINESS-TEST

- 状态：READY_FOR_REVIEW / PARTIAL；仅修复已授权G2收口CI测试稳定性。
- 依据：2026-10-26 Master明确委派，失败run 40279318064（Head `4d5709cc4c529ce3f91a4f9977b2ecbda56371ee`）。当前G2授权索引与总卡继续约束范围。
- Owner：g2_readiness_test_fix；Reviewer：Master另派只读Reviewer；Master唯一main集成人。
- BaseSha：`4d5709cc4c529ce3f91a4f9977b2ecbda56371ee`。
- 分支：`codex/G2-READINESS-TEST`。
- Worktree：`/Users/chasen/.codex/worktrees/g2-readiness-test/ontology-platform`。
- owned_paths：`backend/tests/OntologyPlatform.SecurityTests/G2ReadinessBudgetTests.cs`、`docs/tasks/G2-READINESS-TEST.md`、`docs/evidence/G2-THIN-SLICE-001/readiness-test/**`。
- read_only_dependencies：所有生产源码、其他测试、项目/锁/CI、合同/迁移、共享配置及其他路径；不读取私有runtime/凭证。
- DAG：真实失败调查/复现 → test-only修复 → focused/全Security/native format/SelfTest → 独立Review → Master集成和同Head Linux CI；最后两项由Master完成。
- 假设：生产数据库子预算1秒，整体2秒；固定八次70ms等待叠加首次EF/JIT开销可能耗尽子预算，因此HTTP尚未进入，而原测试预期两个路径。
- 实施：先记录原测试结果，采用真实EF/host预热或可控同步消除冷启动污染，测量期间继续验证八个查询、两个固定HTTP路径、整体取消和严格墙钟阈值；不延长生产预算、不放宽产品断言、不增加依赖。
- 验收：原始冷focused复现；修复focused；全SecurityTests；`dotnet format backend/OntologyPlatform.slnx --verify-no-changes --no-restore`；`pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`；适用native真实构建和测试；生产文件零diff。
- 负例：整体预算若被各阶段重置必须失败；测试I/O隔离不能代表真实PG/Jena/RustFS业务通过。
- 停止：生产缺陷先报告；只在白名单修复；提交push后交Master独立Review，不合并main、不启动浏览器/下游阶段。

## 实际交付

- 冷full-JIT原测试FAIL；预热后相同环境PASS，queries8/http2/2036ms/503/取消；原等待/阈值/断言均保留。
- 全Security114：84成功、30真实依赖未注入而跳过、0失败。
- SelfTest/受锁restore/format/native-all均exit0；7项目共338项，123成功、215依赖未配置跳过、0失败，ASPIRE010/workspace警告保留。
- 原缺parser与证据空白规范前置失败保留；Master批准ignored只读parser缓存复用，无新增依赖。
- 验证和生产零变更证据见 `../evidence/G2-THIN-SLICE-001/readiness-test/verification.json` 与 `production-boundary.json`。生产源逐文件对比基线完全一致。
- 独立Review、Master集成、最终同Head Linux CI、唯一Review ZIP待Master完成；不得宣称本分支已满足集成条件。

Master集成回执：原a02d6da7297b254ce153628f29cf765de10af77c已cherry-pick -x到Master，限定独立审查C0/I0/M0，生产无变更。最终同HeadCI/ZIP由末次实际manifest及独立回执闭合。
