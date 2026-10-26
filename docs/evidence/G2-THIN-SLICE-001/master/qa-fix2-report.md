# G2 QA fix round2 — DRAFT/PARTIAL

本轮延续[round1报告](qa-fix1-report.md)，按Master限定派工和SDD fix-loop实施。BaseSha=`e5f33264b7226c3c9b962f53bf65b28a0884d8c9`；已推送实现Head=`ca5c63de8c6150a772d579ec2f4403bb00d874b3`，分支`codex/G2-QA-FIX`。证据随后独立提交，最终交付Head以Git回执为准。唯一源码写入为`g2-observability.py`及`G2Acceptance.Tests.py`，另有本组`qa-fix2-*`证据；没有改产品源码、启动器、合同、锁、CI、依赖或架构。

读取了Master提供的安全冷启动证据：五个实际Trace已可取，worker creation tag search为空时第12检查失败，round1的FAIL报告与一键停止行为正确；随后同一creation Trace在自有栈重启/等待后可查到一个distinct worker，原25项不改通过。这支持异步可见性是候选解释，不能据此认定出口或索引延迟为唯一根因。本Agent未访问Master私有runtime或容器，真实新冷启动仍由Master验证。

本轮为Trace读取、worker tag search、worker Trace、Loki日志/series与四组Prometheus meter查询设置一个共享90秒单调时钟截止时间，1秒短poll；切换阶段不重置预算。每次真实HTTP timeout为`min(10秒, 剩余秒数)`，收到响应及完成隐私/可见性判断后均复核截止时间，超时后的响应不能变成PASS。

只重试尚无数据，以及暂时网络错误和HTTP408/425/429/500/502/503/504。仅Tempo `/api/traces/` 的404按尚未可见处理；search等其他404及401等非暂时4xx立即失败。JSON解析/必需字段访问错误、错误Trace关联、隐私内容、metric backend status错误、身份/正文维度和有限值合同错误不会进入重试。每一份收到的JSON在判断是否缺失之前先检查隐私，防止含秘密的空结果被重试掉；原25项成功断言保持，指标合同还会在每组非空series到达时提前检查，不能等待其他指标时掩盖已有坏数据。

保留round1开跑清旧PASS/预置FAIL、完整原始导出后原子PASS和异常fail-closed。运行报告新增`visibility`：实际`budgetSeconds`、`pollIntervalSeconds`、总`pollCount`、`elapsedSeconds`及逐请求`polls/elapsedSeconds/state`。这些值由真实执行累计，没有预填产品PASS；永远缺失时保留FAIL并记录timeout。

| 覆盖验证 | 实际命令/结果 | 证据 |
| --- | --- | --- |
| 最终测试对round1固定源码隔离运行，检出无poll/无剩余timeout等缺口 | `python3 scripts/tests/G2Acceptance.Tests.py`，exit1；22 tests，8 failures（含subtests）/1 error | [RED](qa-fix2-red.txt) |
| 包含round1的22项控制面回归，全部通过 | `python3 scripts/tests/G2Acceptance.Tests.py`，exit0；22 tests / 0 failures | [GREEN](qa-fix2-green.txt) |
| 仓库工程检查器自测 | `pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`，exit0 | [SelfTest](qa-fix2-selftest.txt) |
| 现有脱敏/路径负例 | `python3 scripts/tests/Wave2Runtime.Tests.py`，exit0 | [输出](qa-fix2-wave2.txt) |
| 两个修改Python源文件语法 | `py_compile.compile`使用临时`cfile`，exit0 | [语法](qa-fix2-syntax.txt) |
| 差异文本检查 | `git diff --check`，exit0 | 无输出 |

新增测试实际覆盖：Trace/search/Loki/metric先空后出现；search及meter永远缺失到90秒FAIL；第一阶段先耗60秒后search最多剩30秒，最后HTTP timeout为1秒；超时后的成功响应拒绝；暂时503/网络先失败后成功；非暂时401/search404不等待；含秘密的空结果立即失败且无raw导出；错误creation关联/metric状态/有限值立即失败；剩余timeout实际到达真实HTTP opener边界。时钟和I/O为隔离替身，进程编排仍有原先真实子进程exit23的控制面负例。这些只认证验收脚本控制面，不是LGTM、OTel或产品PASS。源散列和状态见[结果清单](qa-fix2-results.json)。控制台归档仅逐行去除尾随空白，未筛选内容。

fix-loop第2轮：本Owner已实现候选修复并提交覆盖测试、命令和输出；是否ADDRESSED由原独立QA Reviewer限定复核。新冷启动真实聚合、原生业务、CI在本树未执行或NOT_VERIFIED；PG timeout仍由HostOwner负责，Monaco仍PAUSED_BY_USER，不涉及付费/云/管理员/生产。Master需查看新cold报告的实际poll与elapsed并核对原全部产品断言，随后决定集成；本报告不提前给出真实cold成功结论。
