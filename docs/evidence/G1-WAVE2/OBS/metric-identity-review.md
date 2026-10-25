# 双实例指标身份整改

状态：DRAFT / PARTIAL。整改前Head=362fc388f84494d70608c84721d1d14a09fca1ab。独立Reviewer指出Important问题，经Owner核实：Alloy的metric资源白名单删除service.instance.id，两个同service.name进程的累计Counter/Histogram可能混写。

[Prometheus官方OTLP文档](https://prometheus.io/docs/guides/opentelemetry/)明确将service.instance.id转换为instance，并与job一起附在各指标序列；keep_identifying_resource_attributes控制target_info额外保留原字段，不取消该转换。[OTel单写者规则](https://opentelemetry.io/docs/specs/otel/metrics/data-model/#single-writer)要求每条流单一逻辑写者，身份缺失可造成累计值伪重置。因此仅在metric_statements保留该属性；日志与Trace资源仍只有原三项，Loki不增加索引标签。Master负责两个API分别注入platform-api-1/platform-api-2；OBS不修改AppHost或SEC。

官方无网络一次性镜像校验见config-validation/20261025T063035Z：Alloy/Loki/Tempo/Prometheus配置exit0，固定ARM64镜像inspect exit0；promtool规则测试exit0，共5场景、7条告警断言和3条查询断言。新增合成输入在60秒验证实例1=6、实例2=12、series数=2及sum=18；此测试只验证PromQL消费语义，未执行Alloy真实双实例入库，不能宣称真实流无冲突。新鲜SelfTest原始输出见verify-metric-identity.json。

统一运行栈后复验：按instance查询两个API的累计请求序列，确认instance仅取platform-api-1/2且Counter/Histogram互不覆盖；再执行sum并记录两条原始样本与聚合结果。受控重启单实例后确认reset只发生在该实例，另一条序列继续累计。真实查询、无乱序/伪重置、Grafana、故障恢复和持久化当前均NOT_RUN。保留以前验证与失败记录；不另起全栈，不生成专项ZIP，不合main。
