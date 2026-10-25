# G1-OBS-001 配置里程碑

状态：**DRAFT / PARTIAL**。日期2026-10-25。实现基线 `87eb51a77bffe7468164a0e418bbbd2e101d95bc`；首个固定资源里程碑 `04a35689de0c7238325cf7c63ccc8737f653b02c` 已推任务分支。Owner仅写OBS白名单；Master唯一注册AppHost。第二里程碑核对固定配置、四中文面板、低基数资源边界及运行手册，并执行新鲜SelfTest。按Master调度结束配置关口以释放Reviewer槽位，工作树保留，真实联调待followup；不另制ZIP、不合main。

| 验证项 | 实际结论 | 证据 |
|---|---|---|
| 五个官方稳定release/许可证/index+ARM64 manifest | OBSERVED：Alloy1.21.2、Loki3.7.9、Tempo3.1.1、Prometheus3.15.1、Grafana13.2.4；原始公开输出及命令exit0 | [官方依赖汇总](dependencies/summary.json)，各组件index.output.json/release.json/license.json/result.json |
| 固定镜像pull | OBSERVED：五项成功；Alloy首轮DockerHub TLS handshake timeout，原错误保留，同摘要一次重试成功 | config-validation各pull.result.json；20261025T055244Z/alloy-pull.result.json |
| 本机已拉取原生平台/用户 | OBSERVED：Linux ARM64；Loki10001、Tempo10001:10001、Prometheusnobody、Grafana472；Alloy平台在最终suite实查 | [镜像必要字段](pulled-image-platforms.json)，最终suite各platform.result.json |
| Alloy/Loki/Tempo/Prometheus官方离线配置 | PASS：四项exit0，无网络、临时容器、固定摘要 | [最终校验](config-validation/20261025T063035Z/alloy-validate.result.json)、同目录其余validate.result.json |
| Prometheus告警负例 | PASS：5场景，7条告警断言与3条双实例查询断言；新鲜不报、缺失/过期报、恢复清除、依赖停启/for窗口；合成双实例分别查询后sum | [最终规则校验](config-validation/20261025T063035Z/prometheus-alert-tests.result.json) |
| 四中文仪表盘/数据源/告警/运行手册/行为事件schema | OBSERVED：配置即代码；JSON/YAML静态检查，未宣称真实面板数据 | [运行手册](../../../development/observability.md)；infra/observability |
| Grafana真实provisioning/中文截图 | NOT_RUN：等待Master统一AppHost | [明确未运行记录](config-validation/20261025T063035Z/grafana-validation-status.json) |
| 正式API→Alloy→Loki/Tempo/Prom查询/一致TraceId与审计ID | NOT_RUN：等待SEC+Master统一运行；未用Console或Running替代 | 后续联调追加原始脱敏JSON |
| 实时故障告警状态/恢复与重启持久化 | NOT_RUN：规则单测不等于受控进程停启 | 后续联合演练 |
| 双实例指标身份整改 | 配置完成：仅metric资源增加受控service.instance.id，Prom映射instance；日志/Trace原三项不动；真实两条series与sum仍NOT_RUN | [整改及复现](metric-identity-review.md) |
| 真实series/index低基数检查 | NOT_RUN：当前仅白名单配置，未用静态配置冒充运行结果 | 后续标签API查询 |
| 完整镜像CVE/SBOM/签名 | NOT_VERIFIED：官方稳定/固定摘要/ARM64不证明无漏洞 | [官方来源边界](dependencies/summary.json) |
| 仓库SelfTest | PASS：exit0；检查器8项、结构化解析正反例4项、环境状态3组、ReviewPackage35项0失败；原生产品测试未运行 | [指标身份整改后复验](verify-metric-identity.json)；先前两次SelfTest记录保留 |
| 同Head CI/独立Review | NOT_VERIFIED：本次为DRAFT/PARTIAL专业分支 | Master后续统一审查/CI |
| RustFS/S3兼容、生产HA/SLO、Windows/Intel | NOT_RUN；仅单节点本地卷，不作相关能力声明 | 运行手册范围 |

实际失败及修复完整保留：首次原始无LF输出/空stderr文本触发仓库格式检查（verify-skeleton.json），改成JSON字符串保留精确stdout/stderr后verify-skeleton-retry.json exit0；Tempo首次 `-config.verify` 缺布尔参数exit2，按实际help改为 `-config.verify=true` exit0；告警初始 `absent` 保留service_name而stale分支聚合掉标签导致真实promtool断言失败（20261025T055050Z），统一 `absent(max(...))` 后20261025T055117Z及最终suite exit0，未删除负例或失败记录。

所有持久服务必须由AppHost启动，OBS未启动第二套Compose/常驻栈。本次临时容器均 `--rm --network none`，仅官方validate/promtool，不处理生产数据或秘密。Grafana无源码默认密码，使用进程/忽略秘密随机注入；匿名/注册关闭。许可证：Alloy/Prometheus Apache-2.0，Loki/Tempo/Grafana AGPL-3.0；完整许可义务在对外/修改前专项审核。本轮用户/Master已批准这些精确LGTM组件的本地开发使用，未增加Kafka/Cloud/额外镜像。
