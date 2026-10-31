# E0 计时切片

Base：e5b7e99715ee7ebfe419717f7cacf0c02dfcb78a。Owner：G3-M5 E0 writer；独立 Worktree / codex/g3-m5-e0。仅本切片四源外的工程工具，不改变产品语义或电源设置。

`task_run_timeline.py` 新写 schema2，新增 timingStatus，将真实子进程 exitCode/outcome/errorCategory 与计时有效性分开。保留原 UTC 回拨，不钳制、不推定睡眠。schema1 历史读取兼容，不改旧记录。只有有效 UTC 区间参与 union/overlap；全体单调累计及已声明依赖的可观察关键路径另列。Agent 活跃/思考、人工等待、未知睡眠为 UNKNOWN。

供真实消费者统一调用：`complete(row, ended_at_utc, duration_ms, exit_code, error_category=None)` 返回 schema2；`append` 保持锁内 attempt 分配。`summary --host-evidence <host summary>` 只报告独立观测窗口及证据 hash，不将不同窗口睡眠扣减命令跨度。

实际短测试：`python3 scripts/tests/TaskRunTimeline.Tests.py`，17 tests / 0 failures / 0 skipped，exit0。覆盖真实进程成功/失败加假墙钟漂移、回拨、schema1/2、非法状态、并发完整追加、参数隐私、独立睡眠证据及无 pmset 平台边界。`git diff --check` exit0。

本结果不等于宿主长会话保障、整栈产品验收或独立 Review。Master 仍需接入 g3-acceptance-runtime 的完成记录、verify 和阶段入口。未运行 Docker、远程 CI、Windows 原生；不新增依赖。
