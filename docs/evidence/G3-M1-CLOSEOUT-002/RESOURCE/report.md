# H3 工程实现报告

范围：单一内容寻址Fuseki来源、Docker精确盘点和本次Docker-only白名单授权；真实旧资源清理由Master统一执行。未删除任何历史Docker资源。

唯一入口 `scripts/maintenance/canonical_fuseki.py` 使用现有Dockerfile全部普通文件字节SHA256固定tag，先验证本地镜像source/context labels；存在时不执行build，不新增history。首次构建TaskId/RunId标签及每次调用ignored receipt；独立Worktree共用主仓artifacts/fuseki-builds/canonical.lock，避免并发首建。AppHost两个原AddDockerfile及g2-integration均调用该入口。`ResourceLifecycle:TaskId/RunId`允许启动者传入非秘密归属，默认DEVELOPMENT/local-guid。无新依赖。

新清理任务 `G3-M1-CLOSEOUT-002` 仅允许docker container/volume/image/history，不允许Git/cache/network。必须同任务已提交CLOSED synthetic证明、全部现有过期/Root/Head/Keep/身份守卫；指纹为`digest(safe_docker_snapshot(type,target))`。卷/镜像还要求显式expectedReferences=[]，操作时检查实际引用；旧卷只接受G2环境已知服务类别，不能凭名称授权。image仅原fuseki:40hex且无引用；history保留原版本/代际/offset/精确no-record持久删除守卫。

`docker_inventory.py`只读取允许字段、准确镜像/卷/容器/history/网络引用、backend generation和logical capacity。不读env、build args或卷内容；每个KEEP须准确ID/理由/解除条件，未知为AMBIGUOUS。`inspect-resources.ps1 -IncludeDocker -DockerDecisionPath <JSON>`接入扩展；JSON按`volume:<name>`、`image:<id>`等键映射分类/reason/releaseCondition。

验证：Canonical 6 unit PASS（先RED缺入口）；Cleanup 44 PASS（新增授权正例先RED Plan identity mismatch；原42全部保持）；Inspector 9 PASS；真实AppHost Release build exit0（既有ASPIRE010 warning）；G3AppHost 2 PASS；真实canonical连续2调用精确image/history集合不变。首次no-restore因新树缺assets失败，随后locked restore与build通过。只读扩展盘点第一次因容器labels字段选择失败，纠正.Config.Labels后重验。真实原生Docker证据见canonical-real-reuse.json和extended-inventory-validation.json。物理APFS回收NOT_VERIFIED；此worker不做真实删除。

真实canonical首次构建保留镜像sha256:05040926259ace989082fac0fb2f52d33f4a8122a9a85cb617eb76965b484a39，context=6bc72da7b5570e60b43cb978965e096fa512befca1e80dbf76ef0710fa681018。逻辑大小不可跨镜像求和；history由Master后续准确盘点处理。
