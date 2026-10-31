# E0 执行前置防线切片

Owner：G3-M5 E0 writer。仅 `execution_preflight.py`、对应短回归及本证据；不写 Master 的入口、公共合同或 host continuity。

|既有失败|最早入口|本切片可执行正反例|
|---|---|---|
|路径/参数猜测|`check_paths` + `check_cli`，容器之前|真实文件与真实 --help 正例；缺路径、大小写、链接、越界、未知参数、解释器缺失和超时拒绝|
|旧 audit action、遗漏 DI|`check_consumers`，真实登记块|现有 impact 动作和 M5 两服务；移除动作/注册或仅留注释拒绝|
|只修 choices 留旧阶段 guard|三入口消费者 AST/登记检查|PowerShell 与 Python 阶段参数、checkpoint/performance集合、M4-only Diff guard、浏览器 M5 派发分别负例|
|重复昂贵失败|`FailureState` 或 `run` wrapper|真实子进程第一次失败、未变第二次拒绝、短复现仍失败后继续拒绝；输入/构建版本变化可跑；短成功可解除旧候选|
|日志/状态隐私|有界状态及固定诊断|不保存原始参数/输出；准确锁/普通文件/损坏格式/既存 partial 保护；Windows/Linux/Darwin平台参与指纹|

失败 fingerprint 绑定 inputFingerprint、testBuildId、testBuildVersion、实际 system/architecture 和固定 errorCategory；不包含 RunId、commandLabel、日志路径。整个执行持锁，同状态并发拒绝。默认不清理旧失败证据，短成功只移除该准确候选；准确原日志仍由调用者按生命周期保留。

`python3 scripts/tests/ExecutionPreflight.Tests.py`：10 tests / 0 failures / 0 skipped，exit0。
`python3 scripts/tests/TaskRunTimeline.Tests.py`：17 tests / 0 failures / 0 skipped，exit0。
`git diff --check`：exit0。

真实基线正例：`python3 scripts/maintenance/execution_preflight.py check --milestone M4 --path backend/tests/OntologyPlatform.SemanticTests/OntologyPlatform.SemanticTests.csproj`，exit0；实际 --help 核对两个 Python 入口。
真实基线负例：`python3 scripts/maintenance/execution_preflight.py check --milestone M5`，exit2，`DI_REGISTRATION_MISSING`，在任何容器/业务请求之前拒绝尚未集成 M5 的组合根。

静态登记检查不能证明实际 DI resolve/事务回滚/请求行为；Master 仍需实际组合根回归、短业务切片和稳定整栈。截图 Schema、日志自扫描、阶段调用接入由 Master 单写，本切片不冒充其已完成。Docker、云 CI、Windows 原生 NOT_RUN，无新依赖。

恢复接口：`FailureState(path,input_hash,test_build_id,test_build_version,error_category='COMMAND_FAILED')` 作为 context manager，先 `allow('short'|'expensive')`，执行真实命令后 `record(cost,exit_code)`。CLI `execution_preflight.py run --state artifacts/<task>/failures.json --input-hash <64hex> --test-build-id <固定测试标识> --test-build-version <真实版本64hex> --cost <short|expensive> -- <真实命令>`。CLI 强制状态在当前树 ignored artifacts 普通目录。
