# G4-ENG-WORKFLOW-001 当前状态

状态：源码及适用验收 READY_FOR_REVIEW；最终 `G4_ENG_WORKFLOW_READY_FOR_CHATGPT_REVIEW` 以包外回执确认唯一V3与独立重开为准。本文件是唯一当前交接，不预填未来ZIP散列。

Base：`709d22ac11880539669d032550a056d7d761dda8`。最终源码：`6475629b4aa305795d7a9937d4edebf749c8e262`；证据提交及交付Head从包manifest读取。分支 `codex/g4-eng-workflow-001`，Master树 `/Users/chasen/.codex/worktrees/g4-eng-workflow-001/ontology-platform`。原M1 ZIP SHA `b82c8db92d0da05d95214f5fe5286f4c6dbdf9ce7e71b936787478bd3d13bf9a` 保持不变，阶段C已核实；main未更新。

授权：[附件03原文](../evidence/G4-ENG-WORKFLOW-001/authorization.md)。固定验收：[EG-01～12](../evidence/G4-ENG-WORKFLOW-001/acceptance-scenarios.json)。目标为幂等环境、影响验收、缓存复用、失败止损、精简证据与工程入口。非目标：业务/迁移/锁版本、M1冻结交付、M2/G6、CI/全局配置、付费服务及main更新。

## 实现和所有权

Master单写根AGENTS/PLANS/现行政策、gate登记、workflow.py、工程入口及本任务证据。环境Writer只写workflow_environment.py及其测试，烟测Writer只写workflow_smoke.py、workflow-smoke.mjs及其测试；独立托管树提交后集成任务分支。业务源码、M1驱动及历史证据均只读。非作者 `/root/reviewer` 已完成源码和不可变复用独立审查。

根入口精简并统一优先级；完整规则见[效率政策](../development/ai-development-efficiency.md)，[gate登记](../development/verification-gates.json)分开默认调度与Full完整输入身份。原显式SelfTest/构包器语义未缩减。

## 实际验证与局限

- Mac ARM64依赖准备：168包/21项目，391 Web包/26,176文件，当前SDK resolver与pnpm本树路径实际核验。环境子树→Master树真实切换时内容键相同、路径键不同；随后OS/Node键及Web独立键修正有定向与真实迁移验证。
- 当前同树重复prepare及正式CLI：exit0，下载/物化/restore均为0。Master共两次实际restore，第二次因身份定义硬化；Writer一次。无相同最终环境的无理由restore。
- API/Web各真实构建一次，OS外网拒绝、no restore，无警告/错误；401运行产物与烟测前后绑定，独立重算一致。
- 真实短烟测：`wf-a4ed156ebbf9`，两检查PASS、0skip：OIDC→UI→API→PG五阶段及缺CSRF403。74.10秒，五容器，卷约278MiB。relay active0，全部自身容器停止。镜像准入/内部网络/fixture权限先前失败及短定位原样保留。
- 完整工程SelfTest一次，exit0，477.47秒；原始命令摘要可解析478项，不冒充全部产品测试总数。后续只变更workflow资格/证据发布/路径预检实现、测试与gate登记；原Full保持旧身份，**不作为当前键REUSED**。非作者接受其未变项＋最终18个定向回归＋当前格式检查的精确差异覆盖，不重复无关Full/M1整链。
- 实际FRESH→Git→REUSED闭环通过：最终源码6475629b，原Run 999e6aeb...，证据64b7cf1a；前一f934证明保留为历史。重新核验原Git源码/日志SHA、平台/工具/政策，输出REUSED且没有新exitCode；仅格式检查FRESH。纯证据变化未触发backend/Web/restore。
- 一条隔离非作者上下文的两个规则决定案例通过：分析不写入、不安装/回main；失败/可变原件不复用，不无条件重跑长链。未声称模型A/B收益百分比。
- 本任务有界电源监测47.6分钟、96心跳，其中82次锁屏且外接显示器熄灭；策略持续满足，任务自有PID已按身份校验精确释放。系统会话连续性仍NOT_VERIFIED，不将无Sleep事件扩大为全程证明。
- CI、Windows、Intel NOT_RUN；`.codex` setup/actions格式未核实，未创建/宣称自动启用。环境准备实现限定已核验Mac ARM64输入；未来任务需其明确运行准入，不自动进入M2。

证据与精确原件恢复见[summary.json](../evidence/G4-ENG-WORKFLOW-001/summary.json)、[validation.json](../evidence/G4-ENG-WORKFLOW-001/validation.json)。初次短命令未统一计时为UNKNOWN；后续workflow复用schema2 JSONL，不将嵌套耗时相加。

## 使用与恢复

```text
python3 -B scripts/maintenance/workflow.py prepare --task G4-ENG-WORKFLOW-001
python3 -B scripts/maintenance/workflow.py plan --base <Base> --head <已检出Head> --output <ignored计划>
python3 -B scripts/maintenance/workflow.py verify --task G4-ENG-WORKFLOW-001 --plan <计划> --publish-evidence
python3 -B scripts/maintenance/workflow.py verify --task G4-ENG-WORKFLOW-001 --plan <当前计划> --reuse <Git索引>
python3 -B scripts/maintenance/workflow.py package-check --task G4-ENG-WORKFLOW-001 --base <Base> --head <Head> --evidence docs/evidence/G4-ENG-WORKFLOW-001/validation.json
python3 -B scripts/maintenance/workflow.py closeout --task G4-ENG-WORKFLOW-001 --dry-run
```

publish-evidence在全部gate结束后发布，避免输出污染同轮输入。可交付原命令输出使用`.txt`，保持原字节并经过既有V3安全扫描，与对应JSON一起提交，再建 `{gate:{commit,path}}` 索引。初次构包在写ZIP前拒绝旧`.log`路径；原Git记录与JSON保持不变，包内等字节文本恢复映射见summary.outputRecoveryMap。未知输入阻断，产品gate没有本任务执行器则NOT_RUN，不隐式调用旧M1整链。

smoke要求当前树已构建API/Web及`artifacts/workflow/<Task>/build-receipt.json`（当前输入键/产物SHA、实际成功构建），然后 `workflow.py smoke --task G4-ENG-WORKFLOW-001`；不能只凭DLL存在复用旧产物。重复smoke不自动build/restore。诊断用verify的`--diagnostic`（≤20秒）；三次同类失败需新相关输入和`--hypothesis`，全部旧失败保留。

## 资源与停止

三个Run各获独立白名单Review并实际删除5容器/4tmpfs卷/2internal网络，合计33对象，准确not-found后验；物理磁盘实际回收字节NOT_VERIFIED。烟测Writer树已原生归档；环境Writer归档被平台“Another active task still uses this worktree”拒绝，KEEP_ACTIVE_REFERENCE，活跃引用释放后再原生归档，不绕过。原命令证据82文件/22,635,039字节已迁移至Master ignored `worker-env-evidence`，索引散列见summary；依赖缓存可再生。

Master树/当前与历史本任务缓存/私有fixture保留供本次审查；解除条件是ChatGPT审查关闭及准确引用/恢复核验。旧M1树、其他任务资源及全局Codex不动。当前下一动作仅最终V3独立重开/交付回执；之后停止，main/M2须单独授权。
