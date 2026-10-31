# Parser Worker 审查交接

状态 DRAFT / READY_FOR_INDEPENDENT_REVIEW，尚未提交/推送，由 Master 组织独立审查。
Base `89667e0`；独立分支 `codex/g6-p0-parser-prep-parser`，托管树 `g6-p0-parser-prep-parser/ontology-platform`。
仅修改 `experiments/g6-p0/parser/**`、`fixtures/**`、`tests/**`；公共合同未改。

本地 Python 3.13.17 / macOS ARM64 标准库测试 35 个 PASS，无 skip；9 种子18片段全回源。
命令与结果见 `parser-tests.txt`，源码 API 和限制见 `../parser/README.md`。

原始未实现/失败日志以 `*.source.json` 保存原字节的 base64、长度和 SHA256；解码 `raw_base64` 可恢复精确 stdout/stderr（含日志自身 EXIT_CODE）。未删改失败事实：最早导入失败；API 占位后26个测试实际执行、29错误；首轮实现6失败1错误。初轮失败中错误码正则漏数字、临时目录根经过 macOS `/var` 链接以及 mock `os.open` 改变支持能力检测的测试前提已修复。生产入口仍逐级拒链接，没有放宽 nofollow。

9 原 seed 及 README/manifest/verify_seed 按字节复制，哈希保持。额外 `edge-cases.json` 以 base64 存坏 UTF-8/CRLF，避免 tracked 文本格式规则改变原件。

资源：1 新托管树+1任务分支 KEEP（未整合且待复审）；每轮安全测试11个准确本次临时目录均由 unittest cleanup 在 finally 等效生命周期中实际回收并断言不存在，包含生成文件/链接/FIFO。没有 Docker/镜像/权重/包/网络/付费API/真实secret，创建/删除均0。没有改变旧树/主线/全局配置。实际磁盘物理回收 NOT_VERIFIED。

正式 SelfTest/静态 verify、证据 Schema、CI（默认 NOT_RUN）、唯一 V3 与独立重开由 Master 在集成任务分支稳定输入后执行。Windows/Linux/Docling/PaddleOCR/OCR/模型/容器实跑 NOT_RUN；合成测试不能作为这些运行时 PASS。
