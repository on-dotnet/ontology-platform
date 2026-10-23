# Worktree实际分配与同步

共同起点：规则里程碑968ab2a3378427cc4f2612ddb1dbb1b60b5ce9e2，已push main。阶段BaseSha为c4679e956d505acd33185e5a289329de67452c84。

| 工作项 | 分支 | 实际规范化路径 |
|---|---|---|
| Master/Integrator | main | C:/Users/Administrator/source/repos/ontology-platform |
| A review_pack_owner | codex/g1-infra-001-review-pack | C:/Users/Administrator/.codex/worktrees/g1-infra-review-pack/ontology-platform |
| B aspire_owner | codex/g1-infra-001-aspire | C:/Users/Administrator/.codex/worktrees/g1-infra-aspire/ontology-platform |

两个树由Codex托管create_worktree创建并注册，无重名冲突；然后分别创建独立分支。目录互不嵌套，main与子树不共用写目录。所有权见任务卡；A/B不能修改根verify/CI/CPM/规则，需求通过消息给Master；B项目内包锁归B，根共享版本归Master。

规则里程碑独立只读审查通过，真实远程CI：run ID 39974991111，[URL](https://github.com/on-dotnet/ontology-platform/actions/runs/39974991111)，commit 968ab2a3378427cc4f2612ddb1dbb1b60b5ce9e2，push，completed/success。不是由空commit status推断。

阶段末清理只在独立审查、最终ZIP归档和安全集成后进行。当前两个树均进行中，不得清理；最终分支/树清单以总报告为准。
