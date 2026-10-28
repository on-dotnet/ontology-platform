# G3-M3 E0工程合同

状态：FROZEN。Master单写共享CI/入口/规范；E0-A工程实现仅下述路径。依据已批准附件及[官方缓存精确审批](../tasks/G3-M3-001-cache-approval.md)。无新包/BuildKit镜像/发布权限/付费容量。旧M2失败事实保持。

## Canonical输入及接口

所有实际Docker构建仍只经scripts/maintenance/canonical_fuseki.py。既有build(task_id,run_id)和CLI --task-id/--run-id/--image-only保持向后兼容；AppHost仍接受ontology-platform-fuseki:context-64hex。新增 --identity（只读输出）、--platform linux/amd64|linux/arm64、--restore-cache <专用目录>、--export-cache <专用目录>。CLI可以组合restore/build/export，--identity不访问网络/不构建。构建输入fingerprint包含schemaVersion、原contextSha256、Jena6.2.0/冻结SHA512、base digest、平台、canonical helper实现hash。tag后缀严格等于完整inputFingerprint（包含helper hash），contextSha256继续是真实源context hash，不把两者混淆。相同输入跨Run稳定；源/helper/platform改变失效。

真实Engine默认平台从docker info的OSType/Architecture确定并规范x86_64/aarch64，不能只看宿主。显式平台必须与实际所建/所验image一致；跨平台归档拒绝。inspect验证Id/source/context/platform/input标签和Os/Architecture；已有错误tag不覆盖。safe_command只记录固定allowlist，不输出原env/buildargs/令牌。

--identity JSON：cacheKey、failureStateKey、envFingerprint、inputFingerprint、contextSha256、platform、image、schemaVersion；CI key=ontology-fuseki-image-v2-<platform规范文本>-<inputFingerprint>，不使用RunId/Head作正常key，不允许restore前缀匹配。镜像缓存只包含image.tar及receipt.json，专用artifacts/fuseki-ci-cache，绝不含runtime/env/卷/凭证。

归档receipt严格schema含：schemaVersion=2、cacheKey/inputFingerprint/contextSha256/platform、image/imageId、archiveSha256/archiveSizeBytes、producerRunId/producerHead、Jena SHA512/base摘要、sourceChecksumVerified（只在冷下载/校验已实际完成时true）。缓存不是独立签名制品：可信push producer与GitHub ref隔离是信任前提；PR只restore，不跨低信任ref保存；不宣称warm再次下载并算SHA512。

恢复先检查普通文件/有限大小/精确schema/输入/平台/归档散列；tar成员路径安全、无links/special/路径穿越/额外tags，Docker manifest config所含image Id/labels/platform必须符合身份，再docker load和inspect。校验失败不计hit；load前损坏记录CACHE_INVALID并安全回退一次冷构建。load后身份不符停止，不自动删除未知资源/覆盖既有tag；按白名单另审。导出只对经过canonical验证的准确image；receipt不能替代load前后的实际校验。CI保存仅可信push且未hit，容量/配额不明阻断保存；保留本地冷构建能力。

CLI日志只输出脱敏receipt，含producerRunId/当前GitHub RunId/runner标识、实际key/imageID、restored/reused/build结果与stages；run A真miss/cold/export，run B同输入不同runId新runner restore且不访问Apache，变更输入必须miss。Action固定restore/save@55cc8345863c7cc4c66a329aec7e433d2d1c52a9，contents:read；PUBLIC仓库缓存占用API已实测无认证200，预算只读查询不发送令牌，不新增权限，不启付费或包发布。无法实际两Run验证则E0-A BLOCKED。

## 阶段与失败止损

每阶段stage/durationMs/outcome/errorCategory/inputFingerprint；network、checksum、extract/COPY、image preparation和cache restore/export分开。Docker外层600s、两官方源各180s/connect15/HTTPS/3跳/无额外retry保持，checksum成功下载但错误立即终止。COPY缺输入先context allowlist检查并准确分类COPY_INPUT_MISSING，不混作发行包SHA512。

固定输入+平台+Engine/Buildx+失败阶段/类别形成failureFingerprint，原日志只hash/size。相同失败候选必须先短复现才能再昂贵构建；保留失败记录与止损状态。新增--failure-state <专用目录>，其中严格allowlist状态只有input/env/failureFingerprint、stage/category、producerRunId/Head、诊断hash/size和UTC，不保存原输出。Master CI在canonical前用同一已批准cache/restore精确恢复cacheKey+-failure-v1-<envFingerprint>（稳定envFingerprint包含Engine/Buildx精确版本/平台，禁止runner唯一ID；--identity先计算并输出failureStateKey）到artifacts/fuseki-failures；canonical失败后即使job失败也用已批准cache/save保存失败状态（可信push限定，不保存成功镜像或秘密）。该失败缓存只作候选止损提示，不提供成功事实；新进程/新runner必须验证并消费同输入同环境状态。不可变首个失败状态足以要求后续候选短复现；输入或环境改变不沿用。短复现总预算20秒：context/COPY/checksum/平台/权限检查立即失败，网络只对固定官方源做最多每源5秒HEAD/连接探测、不下载完整包；同阶段同类别重现则exit2/BLOCKED，不能再跑600s。探测通过允许本次一次真实构建，但旧失败不删除。最终实际门禁可显式--final-gate运行，不能把旧失败缓存判PASS或跳过最终校验。文件/权限/checksum/配置立即拒绝；网络探测有界且不能读取密钥。负例至少网络timeout、两端失败、checksum错、COPY缺失、坏归档/receipt、错平台、miss/hit及恢复失败。

## 浏览器状态（Master/WEB共同消费，Master单写合同）

初始centerView=source；open/new后source；graph按钮必须显式切换且aria-pressed为true、canvas可见；source按钮返回源码。三窄屏面板catalog/source/inspect显式选择，不假设隐藏面板可见。选中IRI保持，dirty保存/取消与权限分别断言；默认source不可自动改成graph来满足旧测试。

快速workspace-smoke.mjs先跑真实OIDC/API+浏览器：默认source→graph→canvas→source→修改→取消→修改→保存→历史修订diff；超时总量短且每步语义选择器，错误/权限状态明确。完整263浏览器前强制Smoke。故障注入改变默认view或隐藏目标，实际短FAIL并记录耗时，恢复后PASS；不吞异常/扩大超时。UI变更同步旧脚本显式目标视图。

## E0-C接口

TaskRunTimeline JSONL：schemaVersion/taskId/runId/stepId/taskType/inputFingerprint/startedAtUtc/endedAtUtc/durationMs/outcome/errorCategory/dependsOn/concurrencyGroup/attempt；只记录受控命令标签不抓聊天/秘密。墙钟取区间union/跨度并分别命名，累计durations单列、并行重叠单列、可观测DAG关键路径和重复次数；Agent活跃/思考UNKNOWN。每条包含exitCode integer|null和commandLabel（固定受控标签，非原始命令参数）；outcome=PASS|FAIL|BLOCKED|NOT_RUN；PASS要求exitCode=0，FAIL为非0或明确异常类且不可0，BLOCKED允许null或非0，NOT_RUN必须null/durationMs=0。stepId在同一task/run内唯一，dependsOn为已知stepId列表、不得自引用或环；跨并发step区间可重叠，依赖结束不得晚于子步骤开始。UTC显式Z或+00:00，end>=start，durationMs由单调时钟真实测得且与UTC偏移差容许<=1秒，否则拒绝；时间跳变标CLOCK_DRIFT而非伪造结果。attempt为>=1整数，同taskType/commandLabel/inputFingerprint重验自动计数。严格未知字段/非法状态/缺字段/重复step/坏DAG/负时长拒绝。采用Python标准库，包装命令记录真实exit/失败；未运行不伪造时间。

证据预检直接复用正式V3 checks/ci规范化实现，历史metadata兼容不提升权威；当前fixture早跑缺多字段/错误Head/status/EOF/ignored/截图边界。变更不得晚至正式Head后才发现可预期Schema漂移。

资源创建登记TaskId/RunId/输入hash/ID/复用/过期及候选；精确生命周期执行器扩展M3归属，默认DryRun、24h白名单/后端代际/准确ID/引用/恢复事实，独立审查后Apply和before-command-exit-after/持久后验。保护8旧G2卷、旧树、私有runtime；不全局prune/restart/改DB。旧11image和2history逐一分类，仅可证明替代/无引用项进入候选。

## 写入所有权

E0-A worker独立托管树：scripts/maintenance/canonical_fuseki.py、scripts/tests/CanonicalFuseki.Tests.py、scripts/tests/CanonicalFuseki.Real.Tests.py、允许新增scripts/tests/FusekiCache.Tests.py、infra/development/fuseki/Dockerfile/fetch-fuseki.sh/.dockerignore、docs/evidence/G3-M3-001/E0-A/**。不修改CI/verify/AppHost/公共规范或其他模块。Master负责接入CI/verify/AppHost及独立Review；需要新公共接口先报告。只读依赖为本合同、AGENTS/PLANS、M2交付、现有AppHost/acceptance入口。worker不能自行合并main。
