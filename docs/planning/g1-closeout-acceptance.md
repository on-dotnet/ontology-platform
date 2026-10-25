# G1 阶段收口验收矩阵

日期2026-10-25；当前关口G1-CLOSE-001，初始Base=d181f66e569e190a66b0f48b179f2fd9390b9467。本文件是增量验收，不重写G0/G1历史；最终实际结果以本轮证据和Review ZIP manifest为准。当前总体PARTIAL，不能因基础能力可用就宣称G1全部范围或G2业务完成。

## 历史状态独立保留

| 任务 | 原记录事实 | 截至本次收口的能力/证据 | 原记录 |
|---|---|---|---|
| G1-ENG-001 | PARTIAL；当时工具缺失/产品NOT_RUN | 精确工具及真实工程已由后续阶段补足，不回改原事实 | [历史报告](../evidence/G1-ENG-001/report.md) |
| G1-INFRA-001 | READY_FOR_REVIEW；当时本机工程PASS | PG/Jena/RustFS/Keycloak开发资源、4宿主测试、持久化与审查包 | [历史报告](../evidence/G1-INFRA-001/delivery-report.md) |
| M0-MAC-PORTABILITY-001 | READY_FOR_REVIEW / PARTIAL | Mac最低工程PASS，Windows/Intel未本轮执行 | [历史报告](../evidence/M0-MAC-PORTABILITY-001/delivery-report.md) |
| G1-SEC-001 | Wave2本地纵向PASS、总PARTIAL | BFF/OIDC/PG会话审计/范围，当前新增审计读取与异常收口 | [Wave2报告](../evidence/G1-WAVE2/master/delivery-report.md) |
| G1-FE-001 | Wave2本地纵向PASS、总PARTIAL | 中文Shell/Base UI/主题/真实平台资源与审计/真实OIDC | [Web手册](../development/web.md) |
| G1-OBS-001 | Wave2本地纵向PASS、总PARTIAL | LGTM/中文基础Grafana/告警恢复，当前诊断收口；非完整中文业务运维中心 | [观测手册](../development/observability.md) |

## G1退出标准逐项

| 原G1标准 | 实际能力与界限 | 本轮状态/负责后续 |
|---|---|---|
| 固定工具链/CI/模块边界 | 当前锁、隔离pnpm、真实solution和独立模块；Linux同HeadCI按manifest | PASS（Mac受锁/Release/format/SelfTest，实际CI待最终Head绑定）；见本轮报告 |
| 真实登录/拒绝/Shell/API/OpenAPI | 已有真实链路，本次必须重跑，审计成功/500合同为增量 | PASS（46安全/4Infra、310协议、UI5/OIDC2、真实OpenAPI）；见本轮报告 |
| PG审计/Outbox | PG会话/登录注销/资源/拒绝审计已实现；本次补audit-read。通用发布Outbox尚无真实消费者/实现 | 审计本轮验收；Outbox NOT_RUN，G2发布事务首次需要时实施，不冒充G1完整交付 |
| Jena/RustFS开发资源 | M0/INFRA有真实资源/探针持久证据；本轮Wave2使用7容器模型，无Jena正式发布/S3完整兼容承诺 | 开发能力历史PASS；Jena正式发布、RustFS各消费者PoC G2/G8 NOT_RUN |
| OTel与中文入口 | 自建LGTM、4中文技术面板和原生安全日志；完整业务查询树/运行中心未实现 | 本轮诊断重跑；完整产品运维 G2-G8分期 |
| 一键启动与安全闭环 | 唯一AppHost；首次prepare/core/bootstrap/full显式阶段，不伪称无需配置的一条命令 | 当前同机开发可运行；生产/新机自动化边界保留PARTIAL |
| 性能可重复基线 | 原请求指标存在，不能代替批准样本/负载/延迟基线 | NOT_RUN；G2前性能样本/预算需新授权，G8正式SLO压测 |
| RUM/行为分析/产品模块 | 仅schema与治理设计，当前无事件接收→存储→漏斗产品闭环 | NOT_RUN，待业务阶段明确同意/保留/采样/撤回/授权后实施 |

## 十四模块实际覆盖

| 模块 | G1已交付范围 | 业务完成度/负责阶段 |
|---|---|---|
| 01 本体资产中心 | 仅共享安全/前端/观测基础 | NOT_RUN，G2草稿/版本资产，G3完整 |
| 02 本体设计中心 | 同上，无OWL/SHACL图形/源码编辑器 | NOT_RUN，G2最小编辑/G3复杂公理 |
| 03 术语标准中心 | 同上，无SKOS业务 | NOT_RUN，G3 |
| 04 AI本体构建中心 | 同上，无抽取候选 | NOT_RUN，G6 |
| 05 文档知识中心 | 同上，无解析/OCR/知识流水线 | NOT_RUN，G6 |
| 06 数据连接映射中心 | 同上，无五源连接器 | NOT_RUN，G4，生产只读凭证需单独批准 |
| 07 实体知识图谱中心 | 同上，合成平台资源不是业务图谱 | NOT_RUN，G2样例/G4真实源 |
| 08 语义验证推理中心 | 同上，无SHACL/推理业务 | NOT_RUN，G2/G3 |
| 09 本体发布治理中心 | 同上，无发布/激活/回滚业务 | NOT_RUN，G2/G3，Outbox/CAS/故障注入 |
| 10 统一语义查询中心 | 同上，资源列表不是语义查询网关 | NOT_RUN，G2/G4 |
| 11 指标规则中心 | 同上，无口径或确定性规则执行 | NOT_RUN，G5 |
| 12 MCP智能体中心 | 研发Agent与产品MAF严格分开；无产品MCP/Agent/SSE | NOT_RUN，G2最小/G7恢复 |
| 13 业务智能应用中心 | 同上，无Q235B推理或真实业务应用 | NOT_RUN，G2样例/G7 |
| 14 平台治理审计行为中文运维 | OIDC/授权/PG审计、资源Shell、LGTM和中文基础仪表盘 | PARTIAL；Faro/RUM/行为闭环/完整业务运维未实现，G2-G8分期 |

## FE准确边界

当前依赖实际有@base-ui/react、Tailwind、Next/React，自研视觉组件和globals.css；不能把风格/交互相似说成已经生成shadcn/ui组件或拆分packages/ui。保持Next + shadcn/ui/Base UI目标；G2首次编辑器按需求登记精确组件/官方生成来源/许可/版本，tokens、基础样式、业务样式分层验收，主题/SSR/键盘/AX/冲突/空错拒绝真实交互通过。未引入组件不空造共享包，也不无授权在本轮装Monaco/Cytoscape等依赖。

## 未完项分期与前置条件

| 项目 | 状态 | 责任阶段/Owner | 前置条件及退出证据 |
|---|---|---|---|
| Windows原生 | NOT_RUN | 平台Owner，后续跨平台复核 | 独立Windows宿主/锁工具/Docker，真实全部命令，不以Linux替代 |
| Intel Mac原生 | NOT_RUN | 平台Owner，后续跨平台复核 | Intel Mac宿主，精确工具/架构镜像/同套验收 |
| 全镜像CVE/SBOM/签名 | NOT_VERIFIED | 平台安全Owner，G8供应链 | 批准扫描器/制品策略/签名信任根，镜像及OS层全清单和漏洞处置 |
| 生产证书轮换/HA/SLO/RPO/RTO | NOT_RUN / NOT_VERIFIED | 安全/SRE，G8 | 批准目标、生产相似隔离环境、旧证书解密/滚动双实例/故障恢复/负载证据 |
| 跨主机Next SSR部署 | PROPOSED / NOT_RUN | 部署架构Owner，G8前ADR | 可信固定HTTPS拓扑与Cookie/转发/SSRF/滚动更新测试，见ADR-008 |
| Faro/行为分析 | NOT_RUN | FE/治理Owner，业务阶段新授权 | 明确同意、事件接收/存储/权限/保留/撤回及真实端到端 |
| 完整中文业务运维中心 | NOT_RUN | FE/OBS，G2-G8 | 有真实语义/执行/文档业务后复用专业诊断，不能以Grafana替代产品 |
| 通用Outbox/持久调度/发布 | NOT_RUN | G2发布Owner | 实际首个发布事务/CAS/重试/幂等/恢复合同，不提前空造 |
| G2首片接口/样例/DAG | PROPOSED，只读准备 | Master，须后续明确授权 | [只读准备](g2-readiness-readonly.md)，本轮不写功能源码/不启动G2 |
| main保护 | OBSERVED protected=false；规则详情NOT_VERIFIED | 人类仓库管理员，另行配置授权 | [建议ADR](../adr/ADR-007-main-protection-proposal.md)，不改套餐/可见性/设置 |

阶段结论必须保留PARTIAL：本轮修复通过只表明两P1闭合及已跑链路不退化；缺失Outbox/业务RUM/生产目标与跨平台验证不通过重命名历史变成PASS。

本次Mac实际结果：两P1收口与授权纵向回归PASS，完整46/4/6/5/2/310、真实LGTM16、七容器持久化14与进程替换/告警证据见[本轮报告](../evidence/G1-CLOSE-001/master/delivery-report.md)。本地结果不替代最终同Head Linux CI与独立总体Review，整体阶段继续PARTIAL。
