# G4-M1-RECOVERY-001 — Codex Master 启动提示词（必须在用户正式批准之后使用）

你是 `on-dotnet/ontology-platform` 项目 Codex Master。

**TaskId**：`G4-M1-RECOVERY-001`。

**本提示词不能替代用户审批。只有用户明确批准本任务“受控 ARM64 镜像层获取、内部合成 PoC AMBER-A1 风险接受及原 P3–P5 恢复”后才执行任何新增下载、Docker run、模型/业务操作。若尚未批准，只能 Plan、只读核对并停止。**

本次唯一正式输入为 `G4-M1-RECOVERY-001-CODEX-INPUT-v1.0.zip`，必须先执行 `python3 tools/verify_package.py <ZIP路径>` 验证 CRC/Manifest/SHA，再阅读 `README-FIRST.md`、`docs/01-EXECUTION-CONTRACT.md`、`docs/02-ADMISSION-DECISION.md`、`docs/03-ACCEPTANCE-AND-MAINLINE.md`、`docs/04-LESSONS-LEDGER.md`、`docs/00-CHATGPT-INDEPENDENT-REVIEW.md`。

本任务是**恢复上一轮真实 G4-M1 已完成的 DRAFT 源码**，不重做产品，不重复几十次已知无结果的远程 license 检索。先 fetch 和核对受保护 main、G4-00、`codex/g4-m1-connection-master` Head `59edb405dfb4acf4d4a259cffdc3551bafa90d2c`，从该 M1 Head 建新的托管 Worktree/`codex/g4-m1-recovery-001` 分支；旧 Master/PG/UI Worktree 保留，不混入 main，也不动 G6。

**R0** 先证明准确镜像 registry/digest、`linux/arm64`、本机 Docker Engine/context、现有 `docker scout` 能力、官方许可证/声明和下载/磁盘/资源预算，记录 before。非作者 Reviewer 核对。

**R1–R2** 若获上述新授权，允许以官方**固定 index digest**、只拉取最多4个已批准 ARM64 运行镜像的必要层做离线 SBOM/许可证取证。未通过取证之前不得执行 `docker run` 或 `compose up`；`registry://` 扫描若读取层也算下载。无未知镜像替换、无额外依赖、无任意域名、无客户数据。

**R3** 对全部实际包、版本、NOTICE及分发义务独立分类：GREEN可合成测试，**AMBER-A1仅在这项风险接受已被用户明确批准且独立Reviewer签字、没有已知使用权冲突时**可限内部合成非分发测试，AMBER-A2/RED停止。正式商用 G8 许可未闭合继续 NOT_VERIFIED。

**R4** 根据 ChatGPT 源码审查先验证并修复 `G4Endpoints.cs` 对缺 `ContentLength` 的 64KiB 请求体限制，加入真实 HTTP 负例；仅小范围补完原G4-M1 Compose/运行器/合成TLS和现有产品代码必要修复。不要增加没有证据的“自动 PASS”脚本。始终保留 G3 冻结合同。

**R5** 恢复原 M1 `P3→P4→P5`：真实 PG/TLS+只读、平台PG、OIDC/HTTP、Catalog、Next/Playwright、状态/租约/取消/审计、49项实际验收，先最短真实链再完整稳定输入。未跑项目记 NOT_RUN，适用本地真实验收与非作者 Reviewer 双重门禁。对单个故障做短复现，不盲重跑全栈。

运行 Docker 只使用本任务专属 `ontology-g4-m1-recovery-001` Compose project/资源ID，保留其他 G3/G6及原 M1 工作树/卷。资源限额按附合同，结束只精确清理已证明独占且不再使用的任务资源；未知资源一律 KEEP，禁止 `docker system prune -a --volumes`、强推或覆盖历史证据。

提交已审源码到任务分支并推送，不合并 main；交付完整 49项矩阵、镜像/许可证审查、独立Reviewer、原始命令/退出码/输入SHA、资源before/after、唯一 Review ZIP V3/Manifest/SHA256/独立重开。

成功且真实验收：`G4_M1_RECOVERY_READY_FOR_CHATGPT_REVIEW`。

阻断且带最小见证：`G4_M1_RECOVERY_BLOCKED_WITH_WITNESS`。

提交后停止，等待 ChatGPT 独立复审。不自动进入 G4-M2。
