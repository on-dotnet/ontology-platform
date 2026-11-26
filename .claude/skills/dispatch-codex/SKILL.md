---
name: dispatch-codex
description: 当 Claude 要把规格明确、可独立实现的任务派给 Codex，或接手正在等待或验收的 Codex 任务时使用。
---

# 派发与验收 Codex 任务

## 1 确定分工

工作量较大、规则清楚、能划定独立文件范围的实现适合派给 Codex，例如按规格实现接口和测试、按界面规范实现页面。几行的小改、需要在多处之间权衡的设计由 Claude 直接做。L2 的设计决策不派给 Codex。

Claude 在理解卡里逐项写明执行者、理由和 Codex 强度，由用户确认分工。并行派发前，Claude 先定好共享类型、路由、i18n 键、跨模块入口函数的调用方与签名，并为新功能准备一条会失败的测试。每个文件只交给一个写入者。

## 2 填写任务单

将下面的模板填好，存到目标 worktree 的 `.verification/codex/<名称>.md`。

```markdown
# <任务名称>

## 背景
目标 worktree：<绝对路径>
用户要完成的事：<使用场景与预期结果>
先读：<规格章节、相关实现、测试及只读参考材料>

## 文件范围
只许改：<逐项列出可修改或新建的路径>
不许碰：<特别指出共享文件、生成文件或其他会话负责的路径>，以及允许范围以外的一切文件。

## 命令限制
禁止任何 git 写操作，包括 git add、提交、推送、切换分支、git stash 和重置。
测试：<二选一。① 不运行 docker 和任何经 ./dev.ps1 执行的命令，测试由 Claude 执行。② 只运行这一条容器测试并回报退出码和汇总行原文：./dev.ps1 test-api tests/<文件>.py；允许使用的 Docker 上下文只有 linux013-rootless；选 ② 时原样附上第 3 节那两段申请提权的话>
除上面写明的测试命令外，不运行 docker 和其他 ./dev.ps1 命令（尤其是 up、down、reset、ci）。
本任务另禁：<命令或"无">
可运行的检查：<命令及适用范围>

## 具体要求
<逐项填写行为、边界条件、约定的入口和必须保留的行为>

## 验收标准
- <给定条件、操作、可观察的预期结果及对应检查>

## 最后报告
用简体中文列出改了哪些文件、各自完成了什么。列出实际执行的检查与结果，有测试就贴汇总行原文。说明没做到或没验证的项及原因，以及拿不准的取舍。
```

## 3 派发与等待

1. 用 `desktop-dispatch:send` 将完整任务单、目标 worktree 的绝对路径和强度交给 Codex。机械改写用 `medium`，按复审意见小修用 `low`，在已定规格内需要做实现设计的用 `high`。
2. 用 `desktop-dispatch:wait` 在后台等待，任务结束时会唤醒会话。等待期间先做不依赖这次交付的事。
3. 需要查进展时用 `desktop-dispatch:status`。运行中也可能显示 `interrupted`，先看目标 worktree 里本次改动的文件是否仍在更新。若仍在更新，继续等待，避免重复派发。
4. 让 Codex 自己跑容器测试可以省 Claude 的额度：把项目目录、允许使用的 Docker 上下文（`linux013-rootless`）和具体的那一条测试命令写进任务正文，只跑测试时派发参数用 `access: "read-only"`，需要改代码时用 `access: "workspace-write"`，并把下面两段话原样写进任务正文。

   > 如果默认沙箱拦住了 Docker，请用你自己的 exec_command 重新提交同一条命令，设置 sandbox_permissions: "require_escalated"，并在 justification 中写明要连接哪个 Docker 上下文、跑哪些测试。审批通过后，在原任务继续执行，回报退出码和测试结果。
   >
   > 如果申请被拒绝，或者等待审批超时：不要重试，不要换别的办法绕过，不要等人来点击。记录被拒绝或超时的原因原文，结束本次测试并直接写最后报告。

   `desktop-dispatch` 新建的任务用自动审批（`approvalPolicy: "on-request"`、`approvalsReviewer: "auto_review"`）：Codex 仍按命令逐条申请权限，由 Codex 的自动审批子代理对照任务正文里写明的授权决定通过或拒绝，不需要用户点击。所以授权要写具体，只写一个上下文和一条命令，不写"需要什么权限就申请"这类笼统的话。申请被拒绝或超时时，测试改由 Claude 跑；任务若停在等用户点击（`wait` 报 `stalled`，例如插件被还原成人工审批），同样处理。

   目前只实测过 `read-only` 下直接写出的 `docker --context linux013-rootless run …` 命令。`workspace-write`、经 `./dev.ps1` 的命令（它内部会多次调用 docker）第一次使用时，先核对审批结论再采信结果。

   任务自己的记录里只有命令和结果，审批结论在自动审批子会话的记录里：`~/.codex/sessions/<年>/<月>/<日>/` 下首行 `source.subagent.other` 为 `guardian`、`parent_thread_id` 是任务 thread ID 的那个文件，最后一条回复是含 `risk_level`、`user_authorization`、`outcome`、`rationale` 的 JSON。

## 4 Claude 验收与提交

- [ ] 对照任务单读完完整 diff，包括未跟踪的新文件全文。核对改动归属和路径，确认 Codex 只改了允许的文件，再逐项核实报告中的验收结论。
- [ ] Codex 自己跑过的测试，核对它回报的命令、退出码和汇总行原文；对不上或没有原文的，由 Claude 重跑。没有实际运行过的不写"已验证"。
- [ ] 重点查三处：测试断言是否被放宽、是否为改一处而改了生成逻辑、关键条件是否用了隐晦写法。
- [ ] 将验收标准、diff 路径和 PR 号或分支名交给 `reviewer` 复审；Codex 没跑或结果对不上的受影响测试，同时由 Claude 按 [verify](../verify/SKILL.md) 运行，PR 描述里注明哪些结果是 Codex 跑的。测试失败时把命令和失败输出原文交回 Codex 修复，Claude 再跑受影响的测试。按复审意见修过的部分交给第二轮复审。
- [ ] 有界面改动时，Claude 按[界面规范第 12 节](../../../docs/ui-guidelines.md#12-走查清单)逐条走查，深色、浅色主题各截一张图并附在 PR 中。
- [ ] 受影响的测试通过、复审没有必须修的项后，由 Claude 提交。提交信息注明哪些部分由 Codex 完成。
