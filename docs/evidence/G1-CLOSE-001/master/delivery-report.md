# G1-CLOSE-001 收口交付报告

日期：2026-10-26（Asia/Shanghai；2026-10-25启动）。状态：**PARTIAL / FINAL_REVIEW_PENDING**。本轮两项P1与Mac授权纵向回归已实际通过，整体G1仍含明确未实施/未验证项。BaseSha=`d181f66e569e190a66b0f48b179f2fd9390b9467`；最终已提交Head及同Head CI以唯一Review ZIP manifest.headSha/runtimeCi为准，避免自引用。不得进入G2。

## 改动与为什么

- 审计成功读取在物化响应前后有明确时序：先按真实范围物化，再提交唯一platform.audit.read，再返回AuditId和200；空结果也记录，INSERT失败不能假成功。本次响应不含自身，后续可见，并发各一条、无递归。
- 同表text[]保存完整授权厂区，SiteId仅兼容单厂。新事件从可信claims/已授权显式范围去重排序；读取需同非空组织、非空数组且完整子集。legacy未知记录保留原始数据但普通API不暴露，不能猜测旧首厂实际范围。迁移Down有新事实（含[]）时拒绝，真实旧schema升级/数组往返/安全Down-Up/拒绝丢失及前向恢复均已测。
- 原生LoggerMessage1003/PlatformRequestFault只保留固定route/category/outcome/status/trace，不接受Exception；普通内部500、明确输入400、依赖503，既有OIDC400/401/CSRF与权限403维持。取消、已开始和二次写失败受控Abort。Kestrel原始OnStarting异常出口在源头抑制，Activity无原文描述/异常事件。
- Alloy固定日志正文、精确字段、Span属性/事件/描述清理。真实LGTM首测发现OTel1.20.1名称使用顶层event_name、默认无数字ID；按精确名称映射固定1003，未启实验开关，独立复审与真实全栈16检查通过。没有加框架/新依赖/新业务模块或公开调试端点。
- 公共DTO/OpenAPI/生成TS同步完整scopeSiteIds与500合同；现有Web业务不重写，仅测试截图/验收证据显式可隔离新目录。恢复脚本加强双API各自ready/同Cookie200前置，原最终401等断言保留；真实旧池503红绿保留，服务器无重试/状态改动。

## 实际结果

| 运行项 | 结果/原始证据 |
|---|---|
| 受锁restore、Release build、format | PASS，0编译错误；保留ASPIRE010/format workspace警告；baseline-restore/final-release-build/final-format |
| 全安全/迁移真实PG+Keycloak | PASS 45/45、0skip；原14+SEC13+OBS17+迁移1；final-release-security |
| Infrastructure | PASS 4/4，final-infrastructure |
| 标准SelfTest | PASS；包含ReviewPackage35正反项；final-selftest/打包前策略复验 |
| Web lint/typecheck/Vitest/build | PASS，6单测；精确Node24.22.1/pnpm11.28.8；final-web |
| UI / 真实浏览器OIDC | PASS 5/5与2/2；ui-playwright-final/browser-oidc；只本轮安全截图，独立headless Edge，无日常profile |
| 五身份协议/双实例/CSRF/注销/越权 | PASS 310项0失败；oidc-protocol |
| 实际OpenAPI | PASS，完整scope数组/500/状态/DTO必需字段/安全方案等语义；openapi-contract-check |
| 原生OTLP→真实Alloy | PASS 15/15；独立实际网络/原生protobuf出口；OBS/alloy-event-identity-green |
| 真正PG仅INSERT故障→LGTM | PASS 16项；Loki精确1003/名称/route/status/category/outcome，Tempo同Trace Error，无marker/运行秘密；Trace d2936135477ad129ac19d754fce7b81a；closeout-observability/loki/tempo/series |
| PG停止恢复 | PASS，503/live200/ready503、双实例同Cookie200后注销两401；dependency-fault。API2旧池503→200真实过渡保留 |
| 七容器/六卷持久化 | PASS 14项；同Cookie、PG审计/KC新登录、Tempo/Loki、Prom历史、Grafana新状态；persistence |
| 真正AppHost/双API进程替换 | PASS；内存原Cookie跨全新PID，证书keyring/PG持久，注销重放两401；api-process-restart/process-ids-* |
| 告警/中文Grafana/指标 | PASS inactive→pending→firing→inactive，精确本树两API、无外部通知；4真实中文基础面板截图、双实例同时间指标总和一致；alert-drill/grafana/metrics-* |
| Git/独立Review/CI | SEC 5d92109、OBS19355e0均已push/专项0未解决；整体审查与最终同Head CI在收口追加，最终以manifest与实际run为准 |

截图仅为真实采样窗口：部分面板显示无数据（如错误Trace列表/未触发时告警），不伪造非空，不据截图替代实际Loki/Tempo/Prom查询。本次实际错误Span以完整Trace原始JSON验证。Grafana是专业基础诊断，不是完整中文业务运维产品。

## 失败与修复证据，不改写历史

- SEC原27项13失败/14通过→27/27；OBS14/14红和边界红→17/17；原生出口身份红15项1FAIL→15/15。
- Master新增500文档红例明确失败，DRAFT Linux CI40204444021也真实失败；SEC集成后完整45与实际OpenAPI通过。
- Master移除迁移Down守卫红例实际失败，恢复守卫1/1绿后全集通过。
- SelfTest首次缺本树PyYAML与console CR/尾空白，按原requirements哈希在项目隔离恢复、仅展示空白规范化并记录散列后通过；检查器未弱化。
- 真正LGTM首测事件身份丢失FAIL，原始调查/故障结果保留，未放宽断言；Owner官方源/原生解析/红绿与独立复审后重启唯一专用Alloy，16项真实绿。
- 恢复脚本仅第一实例ready导致第二实例旧池首次503；强制双实例预热后真实复现注销API1=401/API2=503，按双实例恢复前置加强后原401断言通过。七容器同问题的原失败保留，详recovery-gate-analysis。
- 一次Git TLS瞬断/HTTP2帧错误，命令级HTTP/1.1普通push及只读远端SHA确认恢复；不关闭TLS校验、不改全局配置、不强推。

## 阶段边界/剩余项

[G1退出矩阵](../../../planning/g1-closeout-acceptance.md)保留六历史状态与14模块真实范围。通用Outbox、OWL/SHACL编辑/发布、MCP/Agent/SSE、五源连接器、指标规则、文档知识、完整业务运维均未交付；Faro/行为只有schema设计，不能冒充产品闭环；Base UI/Tailwind自研组件不等于完整shadcn生成组件或packages/ui。

Windows原生、Intel Mac NOT_RUN；全镜像CVE/SBOM/签名NOT_VERIFIED；生产证书轮换/HA跨主机SSR/SLO/RPO/RTO未验证。当前API Web:Origin仅回环HTTP，不能当HA方案；ADR-008列未来前置。main.protected=false仍只读事实、rulesets403套餐限制，ADR-007仅建议，未改设置/套餐/可见性。G2只有接口/合成样例/DAG文档，不含功能源码、进程或模型调用。

当前无系统管理员/全局工具/系统信任/收费服务/生产凭证改动，无新依赖/锁变更；原checkout六个.DS_Store保留。开发栈验收后正常停止，六卷与忽略私有runtime保留以便恢复，不打包。有限扫描不是全面防泄露，审查包按标准重新打开逐成员验证。最终只交一个ZIP，停止等待ChatGPT复审。
