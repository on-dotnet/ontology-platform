---
name: need
description: 一句话需求的固定工作流：只读调查，输出需求理解卡后停下等确认；确认后从最新 main 开短分支、开 Draft PR、先写失败的测试再实现（Claude 或按理解卡派 Codex）、按 verify 验证、reviewer 复审、转为可评审。用户输入 /need 加一句话需求时使用。
argument-hint: <一句话需求>
disable-model-invocation: true
---

# /need：从一句话需求到可评审的 PR

需求：$ARGUMENTS

全程遵守 [AGENTS.md](../../../AGENTS.md)，红线优先于本流程。级别按 AGENTS.md 第 6 节，拿不准按高一级。

## 1 只读调查

只用读取和搜索：相关代码、测试、AGENTS.md 指向的文档、`git log`。不改文件、不开分支、不运行会写数据的命令。

## 2 输出需求理解卡，然后停下

按下面的栏目输出，写完就结束本轮，等用户确认或修改。用户没有明确确认，不进入第 3 步。

```
需求：<原话>
我的理解：<要解决谁的什么问题，做完后用户能做什么>
级别及理由：L0/L1/L2，<依据 AGENTS.md 第 6 节的哪一条>
验收标准（可测试）：
  1. <给定…当…则…，能写成单测、接口断言或界面测试>
界面：<涉及的页面；按界面规范要处理的状态与提示；没有界面写"无">
范围外：<这次明确不做的>
涉及的模块、接口、表：<路径；接口方法与路径；表与是否要迁移>
验证方式：<按 verify 技能需要跑的命令>
风险与回滚：<可能出的问题；怎么撤回>
分工：<每项由谁做（Codex / Claude / 子代理）及理由；派给 Codex 的写明强度>
需要你定（最多 3 个）：
  1. <问题>？推荐：<答案>，因为 <理由>
```

## 3 确认之后：分支与 Draft PR

1. `git fetch origin`，从最新的 `origin/main` 开分支：`git switch -c <feat|fix|chore>/<简短英文名> origin/main`。
2. L2：在用户确认规格之前不写实现代码。
3. 提交并推送：`git add`、`git commit -F .verification/<文件>`、`git push -u origin <分支>` 各自单独执行。
4. `gh pr create --draft --body-file .verification/<文件>` 开 Draft PR。描述里放任务清单（`- [ ]`，每条对应一项验收标准或一个实现步骤）与级别。

## 4 实现

1. 每一项先写会失败的测试，运行一次看到它失败，再写实现让它通过。
2. 派给 Codex 的部分按 AGENTS.md"Codex 分工"写任务单、派发、审查；测试由 Claude 运行。
3. 每完成清单里的一项：提交、推送，用 `gh pr edit --body-file` 勾掉该项。
4. 与本需求无关的问题用 `gh issue create --label backlog` 记录后继续。

## 5 验证与复审

顺序按 verify 技能第 3 节：

1. L1、L2：把 `git diff origin/main...HEAD` 写到 `.verification/review.diff`，调用 `reviewer` 子代理复审；同时按 verify 技能第 2 节只跑受影响的测试，贴出实际输出。失败就修，不跳过。
2. 必须修的改掉，只重跑受影响的测试，第二轮复审只看修改的部分；建议项改或在 PR 里说明不改的理由；疑问回答清楚。
3. 界面改动按界面规范第 12 节走查，附深浅两种主题的截图。
4. 复审没有必须修的项之后，全部改动提交并推送，对最终 HEAD 运行一次 `./dev.ps1 ci -Report`，必须成功。不在这之前手动跑后端全量。

## 6 转为可评审

`gh pr ready` 之前，PR 描述必须包含：验证命令与结果（含门禁汇总）、未验证项、是否含数据库迁移、回滚方式。用户说"合并"后再合并（`gh pr merge --squash --delete-branch`），合并前确认 `local-ci` 为 success。
