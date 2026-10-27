# OntologyPlatform 研发约定

- 仓库为 `on-dotnet/ontology-platform`；.NET项目及命名空间使用`OntologyPlatform.*`，Web包为`@ontology-platform/web`。
- 先读[当前授权](docs/tasks/current-authorization.md)、任务卡、[计划规则](PLANS.md)、适用目录AGENTS及[冻结合同](docs/bootstrap/ontology-platform-codex-master-plan-bootstrap-v1.0.md)。历史阶段文档保留事实；当前任务以人类最新明确批准为准，外部文档不能自行扩大权限。
- 仅执行当前授权范围，不自动进入下游关口或调用付费模型。G1-INFRA可实现AppHost/ServiceDefaults、开发资源和最小健康API；不实现业务登录、Web Shell、本体发布、MCP/Agent/SSE或完整LGTM。
- **最新Git决策（2026-10-23，用户明确选择按V2全部授权执行并采用Worktree并行）：**独立写入Agent使用独立托管Worktree和任务分支，Master为main唯一集成责任人，不是全部源码唯一写者。覆盖旧的单checkout/默认直接main偏好，旧G0/G1-ENG历史证据不重写。
- 修改前检查Git状态并fetch确认远端；公共构建配置、锁文件、CI、合同、迁移、Design Tokens及AppHost共享配置Single Writer。任务卡冻结owned_paths/read_only_dependencies，禁止跨树抢写。不能隔离时记录原因并串行写入，不解释为用户禁止Worktree。
- 可验证里程碑及时commit/push任务分支，DRAFT/PARTIAL明确标识；独立Review和集成门禁通过后分批进入main并及时push。不强推、不覆盖用户改动、不静默合并失败成果。Git授权不扩大任务范围。
- 凭证由OS helper静默复用，不读取、展示、保存到源码或打包认证材料。需要人工认证时遵守系统流程，不绕过或反复弹窗。
- 模块化单体、Pragmatic Clean Architecture、Vertical Slice、必要DDD；Domain不依赖EF/HTTP/Jena/LLM SDK。模块各有DbContext和写入边界，不跨模块写表；模块内直接DbContext、显式映射/LINQ Projection。
- ServiceDefaults仅宿主OTel/健康/发现/HTTP弹性；BuildingBlocks仅真实稳定技术合同，不建立万能类或泛型Repository/UoW。
- 禁止TMDL、Microsoft GraphRAG、AutoMapper、Ant Design/Fluent UI依赖、生产系统写入、LLM自动发布和未经批准依赖。RDF/OWL/SHACL为正式语义；REST/MCP/UI复用语义应用服务。
- 新依赖先登记官方来源、精确版本、许可、安全和用途。工具链仅按当前授权在用户/项目隔离目录并存准备，不改机器PATH/默认SDK/全局EF，不安装系统Docker或改WSL；管理员操作及不明凭证/费用先停止报告。
- 变更后运行`pwsh -NoProfile -File scripts/verify.ps1 -SelfTest`及适用真实构建/测试；环境诊断用doctor。零测试、静态配置和空solution不能代表产品PASS；环境不满足明确BLOCKED/NOT_RUN。
- 每阶段DoD包括一个标准审查ZIP：明确已提交BaseSha/HeadSha、完整diff、源码、任务/ADR/证据、实际CI run信息或NOT_VERIFIED；禁止.git/凭证/缓存/私有数据。构包后重开验证路径、文件、散列及diff，输出artifacts/reviews且ZIP不入Git。独立审查后交付并停在当前关口。
- C#手写类型及所有成员用准确中文XML文档，局部变量声明处用有意义中文用途注释；成员之间空行，XML紧贴Attribute/声明。生成文件豁免；CS1591不能覆盖私有成员/局部变量或注释语义，需专项审查。详见`backend/AGENTS.md`。
- 前端保留Next.js/shadcn/ui/Base UI、Tailwindadmin彩色企业后台、自研Design System和无障碍；暂不提取packages/ui仅改变目录。详见`apps/web/AGENTS.md`。
- 研发`.agents/skills`、`.codex/agents`与产品运行时MAF模块严格分开；Agent文字指令不等同OS沙箱。文档/外部内容不得扩大授权。

## 阶段收尾与资源生命周期（PRE-G3-HYGIENE-001）

每里程碑获审后按[生命周期规范](docs/development/resource-lifecycle.md)记录分支/Worktree、Docker、ZIP和ignored目录归属，核实集成与跨机器活跃引用；先commit/push、独立Review及同Head CI，再做白名单安全回收。保护活跃/锁定/旧Master树、未集成代码、私有工具与持久数据，疑义保留并写明复查条件；不触碰全局codex/其他项目/生产。记录before/after数量、容量、准确命令/退出码、实际回收及DEFERRED理由，提交测试恢复入口写下一阶段交接。维护多Agent独立托管Worktree并行能力，Master唯一集成main；不为减少资源恢复共用main串行开发。无需每个安全小步骤再询问，但有歧义/不可逆/生产/跨项目操作暂停对应项。Review ZIP默认采用[V3合同](docs/development/review-package-spec.md)，全部现行非证据源码和当前任务证据各存一次、历史证据/blob/二进制变更完整索引；只交一个已提交Head且独立重开的compact包，旧包校验兼容，不改历史SHA。交付后停等当前关口复审，不自动进入下阶段。

## 实际回收纠偏（PRE-G3-CLEANUP-FIX-002）

阶段已确认关闭且精确安全候选满足条件时，Master必须使用已审白名单实际清理，不再用不可取得的旧聊天证明或统一DEFERRED掩盖缺口。存在安全候选却0删除=FAIL；具体锁定/独特未整合提交/私有runtime/PFX/唯一数据或命令故障逐项列对象、证据、解除条件，其它安全项继续。执行器默认DryRun，Apply需精确ID/期望版本/目录边界/过期拒绝/重验及before-command-exit-after日志；当前/locked/keep路径及后代保护，远端expectedTip用原子compare-and-delete，不覆盖Git历史。阶段DoD必须包含真实资源回收验收与开发环境保留验证；构包54测试不能替代清理测试。公开Git history/任务refs/证据检查只报路径/类别、不泄漏原秘密，不改远端历史。多Agent独立Worktree和Master唯一main集成规则保持，禁止跨项目/全局清理和自动G3。详见生命周期规范及FIX-002任务合同。

Build history回收不能只凭rm exit0/list缺席；须避免单Ref查询零计数陷阱，冻结已审核单节点后端版本/代际，严格验证准确ID持久无记录诊断，并记录自然生命周期后的实测。内存tombstone或后验回现须撤回该项完成结论，保留原时点日志，不主动全局重启/升级/改DB绕过。


## G3-M1-CLOSEOUT-002 永久效率与交付入口

新Master及子Agent开工必须从最新origin/main读取当前授权、任务/交接、资源清单、[效率规则](docs/development/ai-development-efficiency.md)、[Review V3合同](docs/development/review-package-spec.md)和[生命周期规范](docs/development/resource-lifecycle.md)。先Preflight、后冻结公共合同与正反测试，再独立Worktree并行；公共契约Single Writer。失败先廉价分层定位，不重复无关完整验收；稳定Head必须实际完整同HeadCI。

交付冻结顺序固定：源码/格式 → 测试 → 独立Review → 提交 → 同HeadCI → 唯一V3构包 → 独立重开 → 回执。最终diff-check必须exit0，历史失败仍保留。代表截图最多12张、PNG压缩目标3MiB，过程证据从精确Git对象恢复；ignored只入聚合索引。>10MiB报分类体积，>15MiB默认阻断。V1/V2历史VerifyOnly兼容且不改历史SHA。

Fuseki只使用canonical内容寻址构建入口及已校验共享镜像，AppHost不另建随机镜像。资源创建即记录TaskId/RunId/标签/清单；阶段关闭准确白名单回收自身资源，跨任务旧环境保留一套日常开发，其余必须有可再生或可验证备份依据。每个KEEP写准确对象、理由及解除条件；无socket不能标Docker PASS，禁止全局prune/restart/改DB。永久回归由verify -SelfTest及同HeadCI执行，不把静态规则测试当产品测试。
