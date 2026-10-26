# G2 QA 编排修复 round1 — DRAFT/PARTIAL

本轮只修验收控制面。BaseSha=`65212620c36650dc52df299b618de6e2e838f51e`；已推送实现提交=`369bb61d8c4e0eebfcff7e2bd3b9ef9188ecaed3`，分支`codex/G2-QA-FIX`，独立托管树`/Users/chasen/.codex/worktrees/g2-qa-fix/ontology-platform`。本报告与安全原始输出以随后证据提交归档，完整任务Head以Git交付回执为准。仅这两个验收脚本、新测试及`qa-fix1-*`证据具有临时单写权；Host、共享合同、锁、CI和其他runtime均只读。

一键原先只执行full、G1 runtime-only与性能汇总。现在真实栈存活期间顺序执行full→G1 runtime-only→G2 observability→Trace browser→readiness故障→性能汇总；任一子进程非零立即原样返回并进入既有finally清理。Trace复用`bootstrap-web-tools.ps1`返回的精确项目Node路径。原prepare、core/bootstrap、full启动和仅清理自有launcher的逻辑保留。无需改变PowerShell一键入口，也未弱化任何产品断言。

原观测脚本根据成功断言和最后metric在raw字典中存在推导PASS，因此最后断言后的证据导出I/O异常仍可能落PASS。本轮运行开始先清除旧报告并落FAIL，完整抓取、断言、隐私检查及所有原始导出成功后才原子替换PASS报告。成功报告写入/替换失败保留FAIL；持续无法写入时不保留旧PASS。异常正文继续由既有入口抑制，隐私检查仍在raw导出之前。

控制面测试使用隔离临时目录、合成身份和遥测I/O，以及真实Python子进程的退出码作为外部程序替身。它们只证明编排、错误传播和状态持久化，不能证明真实产品通过。12项测试覆盖六门顺序/Node与runtime参数、每门真实exit23逐一传播和后续门不执行、prepare/core/bootstrap/full与launcher清理、合成I/O完整成功、fetch异常、最后断言后raw写失败、PASS报告写/原子替换失败、初始及持续写失败清旧PASS、隐私负例阻止全部raw导出。

| 实际验证 | 退出码 | 证据 |
| --- | --- | --- |
| 最终12项测试对原Base源码隔离运行，12处失败（含subtests），证明回归能检出缺陷 | 1 | [原始RED](qa-fix1-red.txt) |
| `python3 scripts/tests/G2Acceptance.Tests.py`，12 tests / 0 failures | 0 | [原始GREEN](qa-fix1-green.txt) |
| `pwsh -NoProfile -File scripts/verify.ps1 -SelfTest` | 0 | [原始SelfTest](qa-fix1-selftest.txt) |
| `python3 scripts/tests/Wave2Runtime.Tests.py`，原脱敏/路径负例 | 0 | [原始输出](qa-fix1-wave2.txt) |
| 三个修改Python源文件用`py_compile.compile`写入临时目录 | 0 | [语法输出](qa-fix1-syntax.txt) |
| `git diff --check` | 0 | 无输出 |

环境为macOS ARM64、Python3.13.17、PowerShell7.6.8。首次SelfTest因本树没有隔离PyYAML而exit1；按简报仅将已批准primary `.tools/pythonlibs`作为只读符号链接复用后重跑exit0，没有安装依赖或修改系统配置。首次直接py_compile因沙箱不允许本树`__pycache__`写入而exit1，后改为标准`cfile`临时目录并实际exit0。归档后的SelfTest另检出unittest失败日志自带的一处行尾空格，已仅去除该空格并复验；原始输出内容未筛选。源码SHA256和机器可读命令/状态见[结果清单](qa-fix1-results.json)。

真实聚合、LGTM、Trace浏览器、readiness故障和性能在本树均NOT_RUN，Master需在其自有真实环境执行完整聚合并另派独立Reviewer。本Agent未读取Master私有runtime、未操作容器、未宣称PG生产超时修复；该问题仍归HostOwner。没有原生.NET/Web构建或业务集成的PASS声明；模型、Windows/Intel、生产NOT_RUN，Monaco继续PAUSED_BY_USER。CI为NOT_VERIFIED，不虚报run。最终唯一阶段Review ZIP仍由Master按固定集成Head制作；本修复不额外制造阶段ZIP。
