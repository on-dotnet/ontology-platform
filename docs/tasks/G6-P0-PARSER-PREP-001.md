# G6-P0-PARSER-PREP-001

状态 PREP_VALIDATED_PENDING_FINAL_PACKAGE_REOPEN；仅 PREP。BaseSha=d1a61daffe844475b07705797e3ad325cc3f2945，重新 fetch origin/main 与 HEAD 同值。
Master 分支 codex/g6-p0-parser-prep-master；托管树 /Users/chasen/.codex/worktrees/g6-p0-parser-prep-master/ontology-platform。
Parser 分支 codex/g6-p0-parser-prep-parser；独立托管树 /Users/chasen/.codex/worktrees/g6-p0-parser-prep-parser/ontology-platform。Reviewer 非作者只读。

## 权威、所有权、DAG

本轮人类授权及 input/docs/01、02 优先；G6-00 产品设计只在本轮范围适用。原 current-authorization 保留历史，不修改。
Master 独占：本任务卡、docs/evidence/G6-P0-PARSER-PREP-001/**、experiments/g6-p0/contracts/**、harness/**、supply-chain/**、design/**、README.md。
Worker 独占：experiments/g6-p0/parser/**、fixtures/**、tests/**。公共合同 Master Single Writer，修改先请求 Master。
其余 tracked 路径只读，尤其 backend、apps、infra、scripts、docs/contracts、CI、依赖锁、G3 资产。
DAG：Preflight → contract+negative specification → 非作者 Review → Worker 实现 → 源码 Review → Master 任务分支集成 → 稳定输入适用完整测试 → 提交绑定 → 唯一 V3 → 独立重开 → STOP。

## 验收入口与停止条件

Python 标准库 unittest discovery 分别覆盖 tests 与 harness；附件 verify_seed；verify.ps1 -SelfTest；verify.ps1 静态；git diff --check；test-review-evidence；现有 create-review-package LOCAL V3 与独立 VerifyOnly。
先坏版本/坏编码/越界/符号链接/权限/预算/假密钥泄漏/跨 Task 删除负例，再对应正例。实际命令、退出码、测试数、失败修复、输入绑定保留。
真实 Docling/PaddleOCR/Docker/模型和 Windows/Linux 运行 NOT_RUN；CI NOT_RUN。零测试不能 PASS。
当前 execution_preflight 只接受 M1–M5，G6 参数拒绝 exit2；公共脚本只读，补任务自有适用入口，不冒用 M5 PASS。host_continuity inspect 默认旧 taskId，仅复用只读函数并显式包装 G6 归属；已有用户能源确认见 origin/main current-authorization，当前 AC sleep=0/display=10，未知锁屏实验不填 PASS。
原 main 6 DS_Store、17 个既有树（创建后准确枚举19，先前18口头计数纠正）及旧 Docker/ZIP 全部 KEEP，不清理不明归属。未合 main 的任务树 KEEP 至复审关闭。仅准确自身可再生临时 fixture 自动回收；Docker 本轮预计创建0/删除0。

## 已核实入口（工作目录为 Master/Parser 树根）

- `python3 -B -m unittest discover -s experiments/g6-p0/tests -p 'test_*.py' -v`（Worker交付后预检至少1测试）。
- `python3 -B -m unittest discover -s experiments/g6-p0/harness -p 'test_*.py' -v`。
- `python3 -B experiments/g6-p0/fixtures/synthetic_seed/verify_seed.py`。
- `pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`（输出artifacts/g6-p0/selftest.txt）。
- `pwsh -NoProfile -File scripts/verify.ps1`；`git diff --check`。
- `pwsh -NoProfile -File scripts/test-review-evidence.ps1 -EvidenceFile docs/evidence/G6-P0-PARSER-PREP-001/validation.json -ExpectedHead <testedCommit>`。
Import：测试用文件绝对定位experiments/g6-p0并加至sys.path，不依赖pip安装；禁止下载依赖来修import。

## 源码与交接冻结

非作者源码/设计Review通过，Parser35+Harness37+seed9/18及适用稳定完整验证均PASS；testedCommit见本任务validation.json。源码/合同/输入冻结，此后仅证据/任务文档。最终包PARTIAL保留真实运行时NOT_RUN和安装闭包BLOCKED；正式独立重开回执在artifacts/reviews，完成后停等ChatGPT复审。无main集成授权。资源17原树+2任务树KEEP，精确临时回收与Docker未知项见delivery-report。
