# AI 研发效率与交付规则


> 2026-10-29 人类覆盖授权：[本地优先、按需CI政策](local-validation-policy.md)优先于下文旧的同HeadCI强制条款。增量集成、资源收尾与最终交付以适用本地真实验收、独立Review及已提交源码/输入绑定为门禁；Actions默认手动按需，未运行如实NOT_RUN，费用/权限/依赖边界不变。历史记录不改。
本合同从G3-M1-CLOSEOUT-002起适用于Master、子Agent及换机器后的Codex。人类当前明确授权为上限；禁止借效率扩大业务阶段、调用付费模型或跳过安全。历史耗时和失败事实不重写。

1. **Preflight-first**：编码前核实最新origin/main、工作树/活跃任务、锁定SDK/Node/pnpm/Python、依赖受锁恢复、真实测试入口、Docker socket/容器健康、迁移兼容、OpenAPI/TS生成及基线。基础失败先分类并保存短复现，环境缺失BLOCKED/NOT_RUN，不混作业务失败。
2. **先合同后并行**：Master冻结DTO、错误码、事务、资源命名、证据Schema和owned_paths，正反契约测试及独立审查通过后再派独立托管Worktree。共享配置/锁/CI/迁移Single Writer；Master唯一集成main。
3. **分层测试**：静态/单测 → 模块真实集成 → 纵向E2E → 完整验收。廉价门禁失败先修复；增量只跑受影响项，稳定产品输入跑适用本地完整验收。预先写明命令/退出码/实际测试数；零测试不是PASS。
4. **持续集成**：每个可运行纵向切片审查后及时提交推送并分批集成，首次真实集成不得留到最后。发现兼容或导入竞态先缩小复现，禁止反复整栈盲跑。
5. **证据分层**：失败保存命令、exit、短摘要、关键日志窗口、复现入口。过程截图和全量遥测进本地归档；稳定代表截图按页面/主题/视口最多一张、默认12张/PNG压缩目标3MiB。Git原始证据不删，正式V3只保留关键证据与精确Git恢复索引，ignored按目录/类别聚合。
6. **交付冻结顺序**：源码/格式 → 测试 → 独立Review → 提交 → 本地验证绑定（CI按需） → 唯一V3构包 → 独立重开 → 交付回执。CI必须实查run与engineering/governance-integration两个job及Head；构包失败修对应原因，不改CI事实或重做无关业务。git diff --check必须exit0。
7. **真实效率数据**：记录UTC开始/结束、实现/等待/环境/测试/CI/返工/封包时间；无观测写UNKNOWN。墙钟跨度和活跃工时分列，不从聊天时间推断活跃工时；并行区间不可相加当墙钟。
8. **阶段资源收尾**：开始/结束核对分支、Worktree、Docker容器/卷/镜像/history、ignored和ZIP。本任务资源优先；历史资源逐项归属，保留一套日常环境与确有唯一价值项。精确白名单/期限/指纹/后验、独立审查后Apply。每个KEEP有准确对象、理由与解除条件；有安全候选却0删除FAIL。
9. **防跨会话丢规则**：新Master必须读当前授权、任务/交接、资源清单、本合同、构包与生命周期规范，并fetch最新origin/main。依赖DAG、所有权、进度/实际commit及待审事项持久化Git；聊天不作为唯一恢复证据。
10. **不以速度换安全**：不跳过真实数据库/权限/回滚测试，不以Mock代真实集成，不强推、不全局prune、不未知数据删除、不改历史。socket权限错误须准确报告；物理容量无证据NOT_VERIFIED，未运行平台NOT_RUN。

自动化入口：`pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`包含规则可发现性/EOF、V3完整性、安全清理及canonical构建正反例；CI另执行真实数据库/语义集成。规则测试只证明入口与冻结条款存在，不等于产品正确或真实清理。


canonical构建失败必须原子保留严格allowlist receipt：安全命令/TaskId/RunId/context hash、退出或TIMEOUT/耗时、输出hash/size、有限静态BuildKit阶段和固定错误类别；同时输出同一脱敏摘要供临时CI日志恢复。不能只返回generic REFUSED或只留下临时runner本地路径，不输出原始env/buildargs/秘密，不为了PASS任意延长预算或无限retry。

M2起canonical冷下载采用固定Apache dlcdn/archive同版本主备、原SHA512与HTTPS限跳，每次最多180秒且最多2次；成功下载后坏hash立即失败，不将hash失败当网络fallback。外层600秒保持。CI先canonical冷构建再restore，后续集成必须命中相同内容寻址镜像并记录实际receipt，禁止重复随机build。真实冷构建与cache-hit计数另验，静态规则不是产品PASS。

## G3-M3 E0执行入口

M3起CI在应用restore之前先计算`canonical_fuseki.py --identity`，按精确平台/全部构建输入恢复专用镜像归档，再执行canonical校验。`contextSha256`与包含helper/platform的`inputFingerprint`分别记录；禁止将旧context标签误认为新输入身份。官方cache restore/save固定已批准SHA，restore/save目录必须一致（目录参与GitHub cache version）；不设restore-keys且拒绝非精确matched-key。PR只恢复，可信push才保存。PUBLIC仓库用量API已实测无认证200，预算查询不发送令牌；归档≤512MiB且仓库已有占用+候选≤1GiB才写入，不增权限、不改费用设置、API失败停止保存。总量上限保守低于现有已含配额，不推断账单。

镜像tar/receipt先校验文件、路径、散列、平台、manifest/config/layers及准确image ID，再load与inspect；现代OCI根摘要和旧config摘要区别验证。新canonical禁用额外attestation以保持单运行平台归档。warm继承producer下载校验事实，不宣称本runner又下载并算SHA512。必须保留不同RunId、新runner的真实cold/export与restore/load证据；同run reused不能替代。

失败状态使用独立精确failureStateKey，可信push在canonical失败后仍保存有限摘要；同input/env候选先做≤20秒固定官方源短复现，重现同终态错误则BLOCKED，不能再无条件跑600秒。输入/环境变化失效；最终门禁的`--final-gate`必须显式真实执行。BuildKit重复错误summary不重复累计阶段；中途主源失败后备源恢复不能把最终PASS分类为失败。

完整浏览器链由`workspace-smoke.mjs`前置真实OIDC状态验收，独立短入口为`node scripts/acceptance/g2-live-browser.mjs <本树私有runtime.json> --workspace-smoke-only --smoke-fault-check`；默认source、显式graph/canvas/source、取消/保存、历史diff、窄屏与只读权限均有断言。注入隐藏canvas应短FAIL，恢复后PASS。禁止用默认改graph或吞异常迎合旧脚本。

证据编码早期先运行`new-review-evidence.ps1`生成当前Schema，再用`test-review-evidence.ps1 -EvidenceFile <文件> -ExpectedHead <SHA>`预检；生产构包器共用同一规范化实现，历史metadata保留原字节。截图/ignored边界也须早检。TaskRunTimeline用`task_run_timeline.py run ... -- <命令>`记录真实单调时钟与UTC，CI用`ci --step-id <固定标签> --task-type TEST -- <命令>`自动关联同job前序；`summary --path <JSONL>`分列跨度、区间union、累计、重叠、可观察关键路径和重验。并发append在锁内分配attempt，原始参数/聊天/令牌不入记录，Agent活跃/思考UNKNOWN。
