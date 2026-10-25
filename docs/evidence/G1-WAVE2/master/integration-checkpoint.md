# 集成候选里程碑 · DRAFT/PARTIAL

Base=e930935749bcb88d51abb94db4a41695bbbe6717。全部三线仅合入codex/G1-WAVE2-master候选，未进main。正式API/Governance/SEC测试进入solution，Master生成InitialGovernance迁移及精确锁；原4 InfrastructureTests保留。Wave2单一AppHost模型为新PG+KC+五OBS、两API实例和Next，旧基础设施模式完整保留；Jena/RustFS无本轮业务写入。

实际PASS：Mac根受锁恢复、后端build（保留ASPIRE010）、format、全Web frozen restore/lint/typecheck/6test/build、静态与SelfTest、真实临时PG集成8/8（当时提交版本，后加YARP第9项最终需复跑）。新专用Realm真实创建成功；本机重启后只停止本轮明确两旧容器，保留专用卷，由同AppHost恢复，不操作历史数据。

真实OIDC首跑在PAR断言失败：.NET自动PAR使浏览器URL只有client_id/request_uri，不能按旧driver假设要求state/nonce明文。SEC修验收驱动，保留PAR，状态PARTIAL；无伪造成功。根进程日志执行时先脱敏，再写终端/证据。全部密码随机、证书与keyring仅忽略.tools/security/中，不装系统信任。

尚待PASS：真实浏览器OIDC、协议负例、两实例指标、Loki/Tempo/Prom同请求证据、中文Grafana数据/告警恢复/持久化、独立复审和同HeadCI。Windows原生/Intel Mac仍NOT_RUN，跨平台锁仅恢复检查不等于宿主运行。

恢复后的新PG集成已再次执行：9/9全部成功、0跳过（包括YARP新增负例）；原4基础宿主测试也已重跑。根fail-closed Web四项再次通过，无隐式恢复。
