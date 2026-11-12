# G4-ENG-DELIVERY-002｜唯一状态与实施清单

状态：VERIFIED_PENDING_PACKAGE。2026-11-12 用户明确批准工程交付链收敛；不更新 main。
Base：820855bc239d409b9931bf4e3ba669592afb2123。
开工 origin/main：b3b68500d76ab5965fcc540afb883ca605cb15dd。
分支：codex/g4-eng-delivery-002。
托管树：/Users/chasen/.codex/worktrees/g4-eng-delivery-002/ontology-platform。
Owner：Master 单写；Reviewer：非作者只读，最终入口验收另行派发。

实施：先 D01/D03/D05 红例，统一执行、失败状态、双流原件及早期 V3 预检；再严格报告、分层资格与缓存；最后真实短烟测、独立 Review、唯一 V3、独立重开和包外效率回执。

owned_paths：scripts/maintenance/workflow.py、workflow_environment.py、workflow_web_cache.py、workflow_smoke.py、workflow_m2_web.py、workflow_m2_fixture.py、workflow_m2_build.py、workflow_m2_smoke.py、workflow_m2_evidence.py；最多新增 workflow_execution.py、workflow_evidence.py；相应 scripts/tests/Workflow*.Tests.py；docs/development/verification-gates.json、ai-development-efficiency.md、local-validation-policy.md；本任务卡、当前授权及本任务新证据。apps/web/vitest.config.ts 仅报告与缓存配置。构包器仅必要时复用现有安全预检，最小无副作用入口。

read_only_dependencies：全部产品源码、锁文件、历史 docs/evidence、既有 ZIP、冻结架构合同、生命周期和 V3 合同。禁止新依赖/Skills/镜像下载、全局配置、其他连接器、main 更新。

短命令例外：Git 身份/对象读取、文件元数据/散列、宿主只读策略探针。build/restore/test/fixture/smoke/package 不属于例外。

资源：上述托管树及分支 KEEP（未集成成果；解除条件为复审及明确集成/归档）；原工作区六个用户 .DS_Store 保持原状。任务私有运行资源创建时登记准确 ID，清理不跨任务。

验收 D01–D12 均待执行；CI NOT_RUN。未制作审查 ZIP；尚无产品 FRESH/REUSED 结论。


进展：D01/D03红例已保留；公共通道、严格结果、首份V3预检/恢复已实施；工程18、环境6、smoke14、M2准入13、交付11定向测试曾通过（最终稳定输入仍待统一覆盖）。真实HTTPS13、API短烟测3已执行，后续策略接入改动正补受影响短链。UI机器报告389通过；修复fsModuleCachePath后两次warm prepare下载/物化/restore均0。旧Web六类原件当前解释器重核通过，历史事实未改；自然TTL未重复运行。

宿主：用户本轮确认AC与防睡眠；45秒/10次心跳策略持续有效、无已确认Sleep。未观测锁屏/熄屏，明确NOT_VERIFIED；不从无睡眠推断全会话连续性。

公开证据发布仅精确白名单；commands和私有runtime含合成会话/数据，不整体打包。V3内容/路径预检使用公共runner；Git、散列与宿主只读探针保持轻量。当前仍IN_PROGRESS，未冻结工程Head或生成正式ZIP。


最终源码关口：非作者源码及原件复核通过。首次FullSelfTest exit0，508.845865792秒；原输入保留，后续资格/失败身份与取消增量以定向测试覆盖，不冒充当前Full key。当前一般工程18、环境6、smoke14、M2准入13、交付协议13通过；UI389、HTTPS13、PG1、实际OIDC/CSRF/API取消3通过。当前资格入口PASS；旧Web29/16/119/13/1/19按原Head重核，TTL未重复。

尚待：提交候选后受控plan/verify当前绑定，旧ZIP干净树重开、唯一正式V3、非作者独立重开和包外回执。首次旧包重开因DIRTY_TREE拒绝的事实保留；尚无新正式构包尝试。
