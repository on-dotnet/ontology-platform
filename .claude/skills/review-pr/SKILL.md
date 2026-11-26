---
name: review-pr
description: PR 准备合并时使用，按改动级别确定审查人，核对最终提交、门禁和最新 main，并在合并后更新开发栈与进度议题。
---

# 审查与合并 PR

## 1 确认待审提交与合并权限

在仓库内用 PowerShell 7 操作，先将 `$n` 设为实际 PR 号，再查看 PR 的 HEAD、提交状态和文件清单。

```powershell
$pr = gh pr view $n --json headRefOid,statusCheckRollup,files | ConvertFrom-Json
$sha = $pr.headRefOid
$pr.files.path
$pr.statusCheckRollup | Where-Object context -eq 'local-ci'
```

记录完整的 `$sha`。确认该 HEAD 的 `local-ci` 为 `SUCCESS`。状态缺失、待定或失败时暂停合并，由开发会话按 [verify](../verify/SKILL.md) 完成复审、受影响的测试和最终 HEAD 的门禁。

按实际改动路径对照 `AGENTS.md` 第 6 节，取最高级别。L0、L1 由开发会话在复审和门禁通过后自行合并。L2 由开发会话交付 ready 的 PR、验收标准和已验证的 SHA，到此停下，由主会话或用户审过该 SHA 再合并。`reviewer` 只读复审，只提交发现的问题，合并由相应级别的负责人执行。

## 2 对照改动审查

在该 PR 的 worktree 核对 `git rev-parse HEAD` 等于 `$sha`，相关文件没有未提交改动。保存完整 diff 供审查人和 `reviewer` 阅读。

```powershell
New-Item -ItemType Directory -Force .verification | Out-Null
$diff = ".verification/pr-$n-$sha.diff"
gh pr diff $n --color never > $diff
if ($LASTEXITCODE -ne 0) { throw '获取 PR diff 失败' }
$diffHead = gh pr view $n --json headRefOid --jq '.headRefOid'
if ($LASTEXITCODE -ne 0 -or $diffHead -ne $sha) { throw '无法确认 diff 对应待审提交，请重新获取 PR 和 diff' }
```

按文件清单逐个读实现文件、调用方和测试，对照需求的验收标准核查以下内容。子会话和 Codex 的结论须用对应提交的仓库内容、测试输出或提交状态核实后再转述。

- 对照任务单逐个核对**改动路径**。例外须事先获准，并在 PR 描述中写明。
- 沿调用路径核对**四条红线**。AI 写操作只生成变更集，经人审核才生效。外部数据库只执行只读查询。凭据不在响应、错误或日志中回显。已合并到 `main` 的 Alembic 迁移不得改动、改名或删除，新迁移应兼容上一版程序。
- 对新增或修改的受保护接口，逐个找到**权限测试**中匿名请求返回 401、无权角色被拒和获准角色可用的断言。若替换了骨架测试，确认只移除了本次已实现行为对应的占位断言。
- 对 **Codex 实现**，检查是否放宽测试断言、为让单个用例通过而改动生成逻辑，或用隐晦写法实现关键条件。

有必须修的项就退回开发会话。修正后只复审变动部分，并行运行受影响的测试。复审通过后由开发会话在已提交、已推送的干净工作区对新 HEAD 运行 `./dev.ps1 ci -Report`，再按新 SHA 核对。

## 3 核对最新 main 并合并

没有必须修的项后，由有合并权限的会话在合并前执行以下检查。保留审过的 `$sha`，用它查询最新的 `local-ci` 状态。重新获取远端 `main`，其顶端提交必须是该 SHA 的祖先或与其相同。

```powershell
$current = gh pr view $n --json headRefOid,baseRefName | ConvertFrom-Json
if ($current.baseRefName -ne 'main' -or $current.headRefOid -ne $sha) { throw '目标分支或待合并提交不符，重新审查' }
$state = gh api "repos/{owner}/{repo}/commits/$sha/status" --jq '.statuses[] | select(.context == "local-ci") | .state'
if ($LASTEXITCODE -ne 0 -or $state -ne 'success') { throw '最终提交的 local-ci 未通过' }
git fetch origin
if ($LASTEXITCODE -ne 0) { throw '获取远端失败' }
git merge-base --is-ancestor origin/main $sha
if ($LASTEXITCODE -ne 0) { throw '无法确认待审提交包含最新 main' }
gh pr merge $n --squash --match-head-commit $sha
```

分支落后时，由开发会话同步最新 `main`，复核差异并对同步后的 HEAD 重跑门禁。`--match-head-commit` 锁定已审的 PR 提交。如果另一个 PR 抢先合入 `main`，须重新核对最新 `main` 的祖先关系。合并时省略 `--delete-branch`，远端分支由仓库设置处理。

## 4 合并后更新

1. 用 `gh pr view $n --json state,mergeCommit` 确认状态为 `MERGED`，记下合并提交。
2. 从 `git worktree list` 找到主检出目录，进入该目录并确认当前分支为 `main`。执行 `git pull --ff-only`，成功后在此目录用 PowerShell 运行 `./dev.ps1 up`。只有主检出目录可以运行 `up`。
3. 在对应的进度议题中更新交付记录，写明 PR、合并提交和开发栈的实际更新结果。对本 PR 范围外的遗留问题，用 `gh issue create --label backlog` 创建议题并在进度记录里关联。
