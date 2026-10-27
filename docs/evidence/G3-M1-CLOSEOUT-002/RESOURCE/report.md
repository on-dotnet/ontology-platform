# H3 工程实现报告

范围：单一内容寻址Fuseki来源、Docker精确盘点和本次Docker-only白名单授权；真实旧资源清理由Master统一执行。未删除任何历史Docker资源。

唯一入口 `scripts/maintenance/canonical_fuseki.py` 使用现有Dockerfile全部普通文件字节SHA256固定tag，先验证本地镜像source/context labels；存在时不执行build，不新增history。首次构建TaskId/RunId标签及每次调用ignored receipt；独立Worktree共用主仓artifacts/fuseki-builds/canonical.lock，避免并发首建。AppHost两个原AddDockerfile及g2-integration均调用该入口。`ResourceLifecycle:TaskId/RunId`允许启动者传入非秘密归属，默认DEVELOPMENT/local-guid。无新依赖。

新清理任务 `G3-M1-CLOSEOUT-002` 仅允许docker container/volume/image/history，不允许Git/cache/network。必须同任务已提交CLOSED synthetic证明、全部现有过期/Root/Head/Keep/身份守卫；指纹为`digest(safe_docker_snapshot(type,target))`。卷/镜像还要求显式expectedReferences=[]，操作时检查实际引用；旧卷只接受G2环境已知服务类别，不能凭名称授权。image仅原fuseki:40hex且无引用；history保留原版本/代际/offset/精确no-record持久删除守卫。

`docker_inventory.py`只读取允许字段、准确镜像/卷/容器/history/网络引用、backend generation和logical capacity。不读env、build args或卷内容；每个KEEP须准确ID/理由/解除条件，未知为AMBIGUOUS。`inspect-resources.ps1 -IncludeDocker -DockerDecisionPath <JSON>`接入扩展；JSON按`volume:<name>`、`image:<id>`等键映射分类/reason/releaseCondition。

验证：Canonical 6 unit PASS（先RED缺入口）；Cleanup 44 PASS（新增授权正例先RED Plan identity mismatch；原42全部保持）；Inspector 9 PASS；真实AppHost Release build exit0（既有ASPIRE010 warning）；G3AppHost 2 PASS；真实canonical连续2调用精确image/history集合不变。首次no-restore因新树缺assets失败，随后locked restore与build通过。只读扩展盘点第一次因容器labels字段选择失败，纠正.Config.Labels后重验。真实原生Docker证据见canonical-real-reuse.json和extended-inventory-validation.json。物理APFS回收NOT_VERIFIED；此worker不做真实删除。

真实canonical首次构建保留镜像sha256:05040926259ace989082fac0fb2f52d33f4a8122a9a85cb617eb76965b484a39，context=6bc72da7b5570e60b43cb978965e096fa512befca1e80dbf76ef0710fa681018。逻辑大小不可跨镜像求和；history由Master后续准确盘点处理。

## H3.3 P2 独立审查修复

旧源码事实：私有prepare仅volumePrefix，run不传ResourceLifecycle；除canonical image外普通容器未绑定task/run。补ResourceLifecycle.Prepare在模型注册前冻结同一task/run，Apply对全部ContainerResource创建task/run/service标签，覆盖无独立卷的Keycloak；不读取环境秘密。可信runner prepare把task/run写入新私有runtime同时原子创建非秘密artifacts/resource-lifecycle清单，包含expectedServices和准确expectedVolumes；task默认DEVELOPMENT，可由PLATFORM_TASK_ID或prepare参数指定，run默认唯一prefix。旧私有runtime只读，缺字段时使用当前显式task或DEVELOPMENT+原prefix作为新清单身份，不回写原JSON。

启动传ResourceLifecycle__TaskId/RunId给AppHost；manifest区分PREPARED/STARTING/RUNNING/START_FAILED/EXITED，运行中和退出后仅双label筛选准确ID、允许字段inspect；命名卷仅按准确expected列表读取Name/Driver/CreatedAt/ownership Labels，不读卷字节。API/权限错误为BLOCKED且不输出raw stderr。最多64快照并保留完整observedContainerIds/observedVolumeNames集合，避免观测证据无界增长。保留归属不授予删除权限。manifest中expected不等于observed，EXITED仅表示启动进程结束，不声称资源已删除或健康通过。

P2 RED为6项缺少新函数/参数；GREEN为8项真实临时目录/prepare/runner测试（certificate与Docker调用隔离替身），覆盖无secret落盘、旧私有JSON字节不变、task/run传递、错归属/非法身份/链接拒绝和socket BLOCKED；既有Wave2脱敏与真实Release AppHost2边界回归保持通过，Release构建0错误（原ASPIRE010 warning）。本修复未创建/删除任何Docker资源；本机真实before/after由Master统一负责，不把此fixture当真实Docker验收。

## CI 首建超时的失败证据修复

Master真实CI run40487172435 attempt1在canonical首次构建达到600秒预算退出，业务测试未启动；该失败历史保留，具体远端Docker阶段因当时输出统一抑制而UNKNOWN，不推测网络根因。此修复只完善故障可观测性，不延长600秒预算、不增加自动重试、不改Dockerfile/镜像标签/context digest/依赖/成功stdout。

canonical失败时在ignored artifacts/fuseki-builds原子发布`<run>-<uuid>.failed.json`：TaskId/RunId/context SHA256、安全固定语法command vector、退出码或TIMEOUT、实际耗时、原stdout/stderr字节数与SHA256；仅保留最多12个静态BuildKit阶段/step及固定错误类别，不落原始输出、环境或build args。主CLI把完全相同allowlisted JSON用CANONICAL_FAILURE_RECEIPT标记写stderr，保证ephemeral CI失去本地artifact后可从Actions日志恢复；成功JSON/image-only输出保持原合同。只显式读取且数字校验GITHUB_RUN_ID/GITHUB_RUN_ATTEMPT；不dump环境。锁无论失败均释放，后续明确运行可重试。

TDD RED为未生成失败receipt；GREEN为Canonical共10项（原6+新增timeout bytes捕获、非零build/CLI摘要、inspect不冒建、未知参数抑制与窗口上限），真实temp目录验证原子发布/无partial/锁释放/下一次cache-hit可重试；合成secret不进入receipt/stdout/stderr，receipt与stderr摘要一致。无任何真实Docker创建/删除，不把替身故障模拟当远端故障根因或真实集成通过。
