# 中文开发运维与 LGTM

适用范围为 G1-WAVE2 / G1-OBS-001。版本和镜像索引固定在[资源清单](../../infra/observability/resources.json)，官方发布、许可证与 ARM64 子摘要的实查记录见[OBS证据](../evidence/G1-WAVE2/OBS/status.md)。完整镜像 CVE/SBOM 与签名校验仍为 NOT_VERIFIED，不能将固定摘要解释为没有漏洞。Alloy/Prometheus 为 Apache-2.0；Loki/Tempo/Grafana 为 AGPL-3.0，二次修改/对外提供服务前须专项核查许可义务。本阶段使用未修改的官方镜像。

## 唯一启动与访问

AppHost 是唯一资源编排，由 Master 注册；不另建 Compose 或单独常驻容器。所有容器在同一隔离开发网络，使用 alloy/loki/tempo/prometheus/grafana 固定别名（或等价 Aspire EndpointReference）；主机端口只绑定回环。容器内部监听全部接口供隔离网络通信不代表允许公网发布。正式 API 用 `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:14328`、`OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`，Exporter 间隔5秒；由 SEC 注册 `OntologyPlatform.Api` ActivitySource/Meter，避免第二套遥测。原 Infra Dashboard 继续存在，不作为 LGTM 证明。

| 组件 | 本机入口 | 内部端口/就绪 | 持久卷目录 |
|---|---|---|---|
| Grafana | localhost:15330 | 3000 /api/health | /var/lib/grafana |
| Loki | localhost:13100 | 3100 /ready | /loki（chunks/index/WAL/compactor） |
| Tempo | localhost:13200 | 3200 /ready；4317/4318仅内部 | /var/tempo（blocks/WAL/runtime） |
| Prometheus | localhost:19095 | 9090 /-/ready | /prometheus（TSDB） |
| Alloy | localhost:12345；OTLP14327/14328 | 12345 /-/ready；4317/4318 | /var/lib/alloy/data |

所有卷名为本轮专用 `${VolumePrefix}-组件-data`，不得删除/复用其他项目卷。Loki/Prometheus开发保留3天；Tempo为官方本地存储默认保留期，生产保留策略待评审。Tempo3使用 `target: all` 单体模式，不需要Kafka；仅本地卷，不声称通过RustFS/S3兼容或HA。Alloy持久目录不保证所有在途OTLP批次断电无损；本轮重启验证重点是已查询写入的Loki/Tempo/Prometheus数据，不声称生产RPO。

Grafana禁止匿名访问与注册，管理员名 `platform-dev-admin`，密码由 AppHost 的秘密参数 `grafana-admin-password` 注入 `GF_SECURITY_ADMIN_PASSWORD`，没有源码默认值。每轮新环境生成随机密码，经批准的进程或Git忽略秘密载体注入；复用卷重启保持同一秘密。不要打印完整容器Env、Dashboard token、认证Cookie或秘密文件，不在命令行参数/URL/截图中放秘密。Grafana生产必须TLS、SSO/角色边界与内部代理，开发HTTP不是生产设置。

## 查询与关联

进入Grafana「平台运维」文件夹，四个中文面板为「系统总览」「API性能」「依赖健康」「错误与Trace关联」。界面默认简体中文；插件中尚未翻译的文字可保留。所有面板和告警来自配置文件，无数据时保持“无数据”，不填充样例成功值。专业日志/Trace仅给授权运维者；审计接口由.NET权限控制。

一次真实 API 请求的 `X-Trace-Id` 是联合查询入口。请求关联审计时另返回 `X-Audit-Id`；审计事实保存在PostgreSQL，由有权限的 `/api/v1/platform/audit` 查询，Loki不替代审计。

```text
Loki: {service_name="ontology-platform-api"} | trace_id="实际32位TraceId"
Tempo: GET /api/traces/实际32位TraceId
PromQL: platform_requests_total{service_name="ontology-platform-api"}
PromQL: time() - max(platform_heartbeat{service_name="ontology-platform-api"})
PromQL: up{job="observability"}
PromQL: ALERTS{alertstate=~"pending|firing"}
```

实际 OTLP 归一化后的指标名、标签与日志元数据以原始 API 查询证据为准。Grafana日志详情使用结构化元数据 `trace_id` 内链到Tempo；Trace→日志按service.name+TraceId查询。`auditId`/`traceId`/`correlationId`是可查询结构化元数据，不做Loki索引。不要把trace当Prometheus标签。API日志只允许固定安全模板/状态/事件码，不记录正文、查询字符串、Cookie、Token或秘密Claims；Collector白名单是额外边界，不能修复源头已经泄漏到body的秘密。

Loki日志与Trace资源只保留service.name、deployment.environment.name、service.version，Loki只索引这三项。指标资源额外保留service.instance.id，Master为两个API明确注入platform-api-1/platform-api-2，实例值由编排受控且同一时刻唯一，不使用用户、请求或随机每请求值。Prometheus把它映射为instance，原promote_resource_attributes保持前三项，keep_identifying_resource_attributes=false不取消该身份映射；先保留各实例Counter/Histogram序列，再在PromQL用sum等显式聚合，不能先删身份把多个累计流混写。Alloy对应用指标数据点仅保留有限method/route/status属性。用户/厂区/炉次/TraceId/审计ID不能变成指标维度。路由必须是有限路由模板，不记录资源ID作route。

依据[Prometheus官方OTLP身份映射](https://prometheus.io/docs/guides/opentelemetry/)和[OTel单写者原则](https://opentelemetry.io/docs/specs/otel/metrics/data-model/#single-writer)。两固定开发实例的身份仅在对应进程槽位内复用；扩缩容或资源身份变化需重新评审唯一性/基数预算，不把此两实例约定推广为生产身份设计。真实验收先确认instance=platform-api-1/2各有独立序列及累计值，再执行sum并检查实例重启后的reset行为；promtool的合成输入只验证查询语义，不能证明Alloy实际保留或真实双实例已到达。

## 故障演练与恢复

告警规则位于 `infra/observability/prometheus/alerts.yaml`，Prometheus每10秒评估，本地 `/api/v1/alerts` 和 `ALERTS` 历史序列作为可检索通知记录，不外发邮件/IM，无额外Alertmanager容器。心跳 `platform.heartbeat` 是API每5秒产生的UTC Unix秒 Gauge；`time()-max(platform_heartbeat)>25` 或缺失并持续20秒告警。开发短阈值仅供复现，不是生产SLO。

1. 记录心跳新鲜、API请求指标与各目标 `up=1`，保存UTC时间、查询JSON和明确退出码。
2. 由Master停止本轮正式API受控进程；等心跳过期及for窗口，查询pending/firing并保存。再启动相同配置，确认心跳刷新、告警清除；保留 `ALERTS` 时间范围数据以证明恢复，而不是只保留最终空列表。
3. 选择本轮明确ID的Tempo容器，由Master受控停止；依赖 `up=0` 持续20秒触发「观测依赖不可用」。恢复原容器并保存up=1和告警恢复证据。不得停其他项目容器，不新增公开故障写入端点。
4. 对真实请求先保存TraceId和三个后端查询，再由Master重启相关资源、保留相同卷与秘密；重启后按原TraceId/时间范围再次查询，证明已写入数据保留。不能用重启后新造数据代替旧数据复查。

健康失败先看具体层次：主机端口不可达→AppHost监听/映射；Alloy ready失败→配置/OTTL；Collector导出失败→下游URL/隔离网络；Loki拒绝→v13/TSDB/元数据限制；Tempo缺Trace→OTLP目标/批处理/查询时间；Prom无数据→OTLP接收flag/名称转换/资源标签。Grafana登录成功但面板空不算数据到达。只查看安全必要输出，不dump认证Env。

## 可复现离线校验

```sh
python3 infra/observability/inspect-dependencies.py
python3 infra/observability/validate-config.py --pull
pwsh -NoProfile -File scripts/verify.ps1 -SelfTest
```

依赖核验仅读公开官方release/license/manifest。validate仅无网络的一次性官方容器，结果带时间/argv/退出码与原始stdout/stderr写OBS证据，Grafana全量provisioning要统一AppHost真实启动验证。Prometheus告警规则负例由同一固定镜像的 `/bin/promtool test rules /etc/prometheus/alert-tests.yaml` 执行。完整产品链路、截图、低基数回查、故障恢复与持久化必须另有真实运行证据；静态验证不算这些验收通过。

## 行为事件与 Faro 边界

行为事件合同见[独立事件Schema](../../infra/observability/events/behavior-event.schema.json)：eventId/eventType/schemaVersion/occurredAtUtc/consent/scope/traceId。只有显式同意后采集，scope只包含获授权组织/厂区，不携带真实身份/业务正文/输入文本/完整URL或秘密；未同意时丢弃。未来Faro接收器必须由.NET授权、限流、同意/撤回与留存策略共同约束，使用专门分析存储及幂等eventId，不写普通运行日志冒充可靠Product Analytics。本轮只冻结接口，不实现Faro接收、完整分析或本体业务运维中心。
