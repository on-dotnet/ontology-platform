# AI 研发效率与交付规则

本合同从G3-M1-CLOSEOUT-002起适用于Master、子Agent及换机器后的Codex。人类当前明确授权为上限；禁止借效率扩大业务阶段、调用付费模型或跳过安全。历史耗时和失败事实不重写。

1. **Preflight-first**：编码前核实最新origin/main、工作树/活跃任务、锁定SDK/Node/pnpm/Python、依赖受锁恢复、真实测试入口、Docker socket/容器健康、迁移兼容、OpenAPI/TS生成及基线。基础失败先分类并保存短复现，环境缺失BLOCKED/NOT_RUN，不混作业务失败。
2. **先合同后并行**：Master冻结DTO、错误码、事务、资源命名、证据Schema和owned_paths，正反契约测试及独立审查通过后再派独立托管Worktree。共享配置/锁/CI/迁移Single Writer；Master唯一集成main。
3. **分层测试**：静态/单测 → 模块真实集成 → 纵向E2E → 完整验收。廉价门禁失败先修复；增量只跑受影响项，稳定Head跑完整同HeadCI。预先写明命令/退出码/实际测试数；零测试不是PASS。
4. **持续集成**：每个可运行纵向切片审查后及时提交推送并分批集成，首次真实集成不得留到最后。发现兼容或导入竞态先缩小复现，禁止反复整栈盲跑。
5. **证据分层**：失败保存命令、exit、短摘要、关键日志窗口、复现入口。过程截图和全量遥测进本地归档；稳定代表截图按页面/主题/视口最多一张、默认12张/PNG压缩目标3MiB。Git原始证据不删，正式V3只保留关键证据与精确Git恢复索引，ignored按目录/类别聚合。
6. **交付冻结顺序**：源码/格式 → 测试 → 独立Review → 提交 → 同HeadCI → 唯一V3构包 → 独立重开 → 交付回执。CI必须实查run与engineering/governance-integration两个job及Head；构包失败修对应原因，不改CI事实或重做无关业务。git diff --check必须exit0。
7. **真实效率数据**：记录UTC开始/结束、实现/等待/环境/测试/CI/返工/封包时间；无观测写UNKNOWN。墙钟跨度和活跃工时分列，不从聊天时间推断活跃工时；并行区间不可相加当墙钟。
8. **阶段资源收尾**：开始/结束核对分支、Worktree、Docker容器/卷/镜像/history、ignored和ZIP。本任务资源优先；历史资源逐项归属，保留一套日常环境与确有唯一价值项。精确白名单/期限/指纹/后验、独立审查后Apply。每个KEEP有准确对象、理由与解除条件；有安全候选却0删除FAIL。
9. **防跨会话丢规则**：新Master必须读当前授权、任务/交接、资源清单、本合同、构包与生命周期规范，并fetch最新origin/main。依赖DAG、所有权、进度/实际commit及待审事项持久化Git；聊天不作为唯一恢复证据。
10. **不以速度换安全**：不跳过真实数据库/权限/回滚测试，不以Mock代真实集成，不强推、不全局prune、不未知数据删除、不改历史。socket权限错误须准确报告；物理容量无证据NOT_VERIFIED，未运行平台NOT_RUN。

自动化入口：`pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`包含规则可发现性/EOF、V3完整性、安全清理及canonical构建正反例；CI另执行真实数据库/语义集成。规则测试只证明入口与冻结条款存在，不等于产品正确或真实清理。


canonical构建失败必须原子保留严格allowlist receipt：安全命令/TaskId/RunId/context hash、退出或TIMEOUT/耗时、输出hash/size、有限静态BuildKit阶段和固定错误类别；同时输出同一脱敏摘要供临时CI日志恢复。不能只返回generic REFUSED或只留下临时runner本地路径，不输出原始env/buildargs/秘密，不为了PASS任意延长预算或无限retry。

M2起canonical冷下载采用固定Apache dlcdn/archive同版本主备、原SHA512与HTTPS限跳，每次最多180秒且最多2次；成功下载后坏hash立即失败，不将hash失败当网络fallback。外层600秒保持。CI先canonical冷构建再restore，后续集成必须命中相同内容寻址镜像并记录实际receipt，禁止重复随机build。真实冷构建与cache-hit计数另验，静态规则不是产品PASS。
