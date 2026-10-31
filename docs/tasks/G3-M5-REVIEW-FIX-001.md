# G3-M5-REVIEW-FIX-001 任务卡

状态：READY_FOR_REVIEW / PARTIAL（唯一V3独立重开以包外回执为准）。唯一授权为本会话用户及[附件V2](../evidence/G3-M5-REVIEW-FIX-001/authorization-v2.md)。Base=580d73e7c0fb38b94dbbed1136ee0b1d24fadc9d；任务分支 codex/G3-M5-REVIEW-FIX-001；托管树 /Users/chasen/.codex/worktrees/g3-m5-review-fix/ontology-platform。

Owner=Master；非作者 Reviewer=独立 quality_reviewer（GPT-6.1 Sol / high，派发实参以回执为准）；Master 实际模型/强度未由工具核实，不伪称已切换推荐 Astra/high。无 Worker，最多 Master + 一 Reviewer。Reviewer 无 owned_paths，禁止写代码；角色文字不能冒充 OS 只读沙箱。

owned_paths：apps/web/src/features/ontology/expression-tree.tsx、expression-model.test.ts；必要本任务定向浏览器测试；docs/tasks/G3-M5-REVIEW-FIX-001.md、docs/tasks/current-authorization.md、docs/evidence/G3-M5-REVIEW-FIX-001/**。公共文档 Master Single Writer。read_only_dependencies：其余源码、全部合同/DTO/OpenAPI/生成物、锁文件、依赖、设计令牌、后端、CI、历史证据及其它树。其他 Agent/用户可能工作，不撤销其改动。

DAG：Preflight → 合同裁决 → 非作者动源码前 Review → 最小 UI 修改 → 定向组件/类型/lint/真实浏览器及 verify SelfTest → 非作者 diff/证据 Review → 提交/推送 → Master main 集成 → LOCAL schema2 输入绑定 → 唯一 V3 → 独立重开 → 回执并停止。

正反验收：历史 RELEASE 当前策略 v4 与独立投影 v1 明确可见且不冒充发布时版本；DRAFT 对应保存时快照澄清；保留转义、固定 ID/hash/source/权限及预算已有测试。真实入口 pnpm --dir apps/web exec vitest run src/features/ontology/expression-model.test.ts、typecheck、lint、适用 build/Web 回归与 scripts/verify.ps1 -SelfTest。真实浏览器入口须先核实；后端复用需要精确测试提交及输入比较，不声称本轮重跑。

历史失败最早防线：错误 milestone → execution_preflight.py check --milestone M5（支持 M1–M5，不接受 G3-M5）；新树无工具 → 核实工具与锁依赖再恢复；证据格式 → test-review-evidence；发布 ID → 固定 manifest.releaseId；相同昂贵失败先短复现，原失败保存。无新 API/action/DI/阶段消费者改动；现有 M5 preflight 静态检查 PASS 不代产品验证。

资源：原主树六个未跟踪 DS_Store 保留，16棵既有附属树保护；仅本任务树/分支及后续确实新建资源登记，不清旧 G2/G3、私有 runtime/PFX。当前宿主 AC sleep=0/display=10，复用原 E0 锁屏熄屏实测；不重跑93分钟监测，不改全局电源。新会话有界观察结束精确释放。

停止：需更改冻结后端/DTO 语义则 CONTRACT_CHANGE_REQUIRED；真实环境/缺陷未解决则 BLOCKED；全部门禁后 READY_FOR_REVIEW，等待 ChatGPT，不启动 G4/G5/G6、不调用付费模型、不解禁 Monaco。

已审源码testedCommit=205e6512f635e55baf7bcb1e764fb209e531c6d3，已push任务分支并ff进入main/push。适用本地验收与非作者Review通过；原浏览器/格式失败已保留并精准修正。仅任务证据收尾，不改产品输入。准确项目8卷已实际Apply，旧8卷保留。恢复见本轮test-matrix、validation、resources及backend-reuse-binding；最终Head/唯一ZIP/hash/重开取包外receipt，防循环回填。
