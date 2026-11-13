# G4-M2-DORIS-01｜一页交付状态

**READY_FOR_REVIEW（本机开发合成范围）**。沿用原会话、`codex/g4-m2-doris-01`、原托管工作树；基线与main为`11595ecb6560f7ed6ceca54666d32b7afcae7f35`，未更新main。

| 交付项 | 结果与边界 |
|---|---|
| 产品源码 | DORIS_READONLY Adapter、凭据录入/单次绑定/轮换/禁用、UI、auditor脱敏、配置及部署说明；固定本机目标，G4生产Guard保留 |
| Compose | 1FE＋1BE单机；FE4GiB/BE6GiB；可复用配置来源，生产覆盖层仅静态参考。本机平台配套PG/OIDC有独立已批网络边界 |
| 当前执行 | 38单元、17wire、24Doris定向、8组真实生命周期、PG1/HTTPS13、真实过期证书拒绝及恢复读取各1；不将重叠计数相加 |
| 有效复用 | 120项UI原件及精确Web输入重新核验；历史自然TTL和共享probe审计回滚按未变方法/原件窄复用，不冒充Doris专属故障注入 |
| 工程与独立审查 | 12项受影响门禁；C#格式、前端类型/lint；原非作者Source Review PASS；最终唯一V3及独立重开回执随交付 |
| 资源 | 四服务峰值预算11.5GiB，生命周期宿主峰值约1.34GiB；测试容器/进程/网络已回收；4个合成数据/日志卷、私有原件和未合并工作树KEEP至审查结束 |
| 未覆盖 | CI、Windows/Intel、生产NOT_RUN；在线撤销、完整SBOM/全量CVE、用户自行拉取网络流量NOT_VERIFIED。仅DORIS-LOCAL-01，不接受生产/分发风险 |

**准入申请：无新增待批事项。** A–F及后续网络/VM/严格TLS差异授权已执行；后续停在当前审查关口。验收和生产沿用用户已有Doris集群，本轮不连接这些集群、不解除G4生产限制。

[正式本地验证](validation.json) · [原件索引](product-proof-index.json) · [独立源码复核](source-review.md) · [部署说明](../../deployment/doris.md) · [风险与未知项](runtime-risk-register.md)

历史原生VerifyFull接受过期证书、环境/格式及夹具失败均保留；严格回调验证经过用户批准和真实正反例。私有口令、密钥、原数据库dump未提交或打包。用户两项DS_Store保持原位置/原字节，仅在交付命令内准确排除，不修改全局Git配置。
