# SEM-A 首个真实API子闭环

状态：PARTIAL，可供Master首次真实API联调与独立Review；尚未认证全Slice A/GATE-A。Owner /root/sem_a，独立托管树g3-m4-sem-a，分支codex/g3-m4-sem-a，公共基准e0662a3（主阶段Base3992582e）。

已实现IG3IdentityTimeService、按源精确编辑、原SaveCore所有写通路CAS锁内scope/history复核、逐声明有效历史保护、非法初稿修复、v4受控OWL-Time及显式身份诊断、LegacyM3工厂和v1-v4正式策略精确分派。保持四源唯一权威、原PG修订/事务审计/命令幂等及发布Outbox，不新建表/迁移/依赖。不推断sameAs，不执行通用时间或OWL推理。

真实窄验：`PLATFORM_TASK_ID=G3-M4-001 PLATFORM_EVIDENCE_DIR=docs/evidence/G3-M4-001/SEM G2_TEST_JENA_IMAGE=<已验证canonical镜像> python3 scripts/acceptance/semantic-roundtrip.py --postgres --filter FullyQualifiedName~G3M4 --label first-identity-real` exit0；31成功/0失败/0skip。测试使用真实临时PG/Jena与迁移；Fixture中的首次不存在migration表诊断随后成功应用，不是测试失败。所有临时容器准确Task/Run标签、before-command-exit-after及强no-such后验见first-identity-real.json；TTL为本次finally立即回收。实际新源输入指纹与monotonic计时见timeline.jsonl。

编译：模块Release 0warning/0error；锁定solution restore、SemanticTests Debug build真实0warning/0error。初始两次构建的自动timeline未采集，耗时/活跃时间UNKNOWN，不推断。后续正式窄验已有自动计时。格式仅变更C#，git diff --check exit0。

专用结构编辑：历史破坏优先409 identity_history_immutable；身份范围403 identity_scope_forbidden；非法新输入按固定类别优先级返回422 identity_ambiguous/time_interval_reversed/time_timezone_required/time_lexical_invalid/time_reference_missing/time_template_unsupported/identity_claim_invalid/event_time_invalid；未知关系identity_relation_indeterminate。所有诊断读取保留真实source/hash/focus/path，无法唯一定位bundle/null行列。普通源码保存可保留语义错误供专家修复，但不能扩大scope或破坏此前有效身份；插入无关错误不能解锁旧有效claim。

待完成：真实PG/Jena/RustFS新v4发布/正式读取/旧v3回滚；权限/并发和批次边界补充；受影响旧测试整体回归；独立实现Review及Master实际浏览器/GATE-A/main。CI NOT_RUN，Windows/Intel原生NOT_RUN。源码和fixture无私有runtime/凭证，脚本公共路径由Master负责，尚未开展Slice B。
