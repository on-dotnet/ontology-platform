# G2-OBS-SUPPORT 有限观测维度实施卡

status: approved/in_progress，当前G2授权的最低观测与安全验证，不启动新OBS业务关口或完整监控产品。Owner=g2_observability；独立Reviewer另派；Master唯一main集成人。独立树g2-observability，branch codex/G2-OBS-SUPPORT；Base b27bfc6之后本卡提交。

owned_paths：infra/observability/alloy/config.alloy；全新scripts/acceptance/g2-metric-boundary.py；docs/evidence/G2-THIN-SLICE-001/OBS/**。Master明确临时将collector唯一写权交此Owner，期间Master不写此文件；其他全部监控配置/资源清单/既有测试/Host/业务代码/锁/依赖只读。不派子Agent/自己Reviewer，不改main，不动用户历史卷/旧runtime/认证材料，不加任何依赖/系统安装/付费资源。

问题：现metric keep_keys只有G1 HTTP维度，实际G2产品的capability/status/operation/outcome/phase会全部被collector清除，不能用本机MeterListener代替真实出口证明。新有限维度应从实际源码固定值枚举，不简单保留任意值导致Prompt/主体高基数泄露。Source：Ontology的operation=AnalyzeAsync/ValidateAsync/ApplyEditAsync/DeployAsync/VerifyAsync/ReadPublishedAsync/ReadVerifiedPublishedAsync（仍逐源码核实）、outcome=completed/failed；Publishing sourceRecord五处固定publish/rollback/outbox与allowed/failure、lease/verify/consume/commit/prepare_or_commit；Query status=Found/Empty/Partial/Unavailable/Unauthorized/Ambiguous、capability固定三ID；Agents源码尚在89510fe（git show只读），agents.run.count outcome=completed/failed，capability三ID。Root单写负责AddSource/AddMeter实际注册，不在此任务改Host。

只增加已核实的低基数有限键和值规则，非法值/敏感正文/用户、site、release、trace/请求ID等不能成为指标标签。保留原G1两个实例service.instance.id以及既有HTTP标签的语义和全部隐私规则。log/trace清理不为了指标放宽；如果发现实际新泄露需报告Master，不自行重构原管道。

先以实际锁定Alloy容器构造有意义RED：发送同一真实OTLP metrics，固定有效维度应该出口但当前丢失；非法值/secret-like标记/高基数键应始终不出口。再最小OTTL修复，实际容器validate及同出口GREEN。使用既有批准Alloy/Prometheus镜像精确摘要与标准库测试工具，可沿用G1原生OTLP二进制sink/真实Prometheus小fixture；禁止加SDK/validator包、全局工具或复制旧凭证。临时资源随机新名、回环端口、限内存/CPU，finally只清本人新资源，不能Docker prune。若test夹具仅合成OTLP而非真实产品meter，必须明确界限，Master后续真实全栈产品再验证。

记录实际命令/退出码/数据点/有限值正反计数、config SHA、容器版本/清理与NOT_RUN，先红后绿，format/仓库SelfTest（可ignored symlink Master既有.tools/pythonlibs复用PyYAML6.0.3，不新安装）；及时源码commit/push DRAFT，独立证据与implementation-report.md后释放slot。最终产品G1/G2同Trace/Loki/Tempo/Prometheus/非泄露/series索引由Master实际验收，不能从此局部绿宣布整体PASS。
