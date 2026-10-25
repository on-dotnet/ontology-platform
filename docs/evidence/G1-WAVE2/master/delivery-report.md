# G1 Wave2 Mac V2 集成交付报告

状态：**PARTIAL / READY_FOR_REVIEW**；本机批准的SEC/FE/OBS纵向功能验收PASS，未验证的跨平台/供应链/生产事项保留。日期2026-10-25。BaseSha=e930935749bcb88d51abb94db4a41695bbbe6717；最终已提交Head与同Head CI以Review ZIP manifest.headSha/runtimeCi为准，避免报告预知自身提交的循环。只执行G1 Wave2，不进入G2。

## 已交付能力

- SEC：正式OntologyPlatform.Api，YARP同源BFF、Keycloak code+PKCE/PAR、HttpOnly引用Cookie、PG加密服务器票据和原子登录/注销审计，组织/厂区/角色校验，CSRF原生form注销、可信代理及生产Host失败关闭，独立live/ready。模块仅Governance schema；原4 InfrastructureTests保留。
- FE：真实Next16/React19/Tailwind4/Base UI中文彩色Design System、深浅主题、响应式Shell、加载/错误/无权、服务端Cookie转发、真实资源/审计视图。Kiota真实PoC后使用冻结OpenAPI类型+内置fetch，不引预览runtime或Hey API。移动关闭导航inert和键盘/AX负例已修。
- OBS：固定摘要的自建Alloy/Loki/Tempo/Prometheus/Grafana；唯一AppHost模型、7容器/6持久卷、回环绑定、中文4面板/规则即代码、真实同Trace检索和有限实例指标。PG审计不由Loki替代；行为事件schema独立于运行日志；未声称RustFS S3兼容。
- Master：独立Worktree与冻结合同、公共DTO/运行时OpenAPI语义门禁、根锁/迁移/solution/CI、隔离工具链、执行时脱敏和可复验生命周期脚本。未改系统工具、管理员信任、GitHub保护规则或生产数据。

## 实际验收矩阵

| 项目 | 结果 | 证据 |
|---|---|---|
| Mac受锁restore/build/format | PASS，保留ASPIRE010；无编译错误 | final-restore/final-build/final-format及最终策略增量日志 |
| Web独立lint/typecheck/test/build | PASS，Vitest6/6；冻结恢复、无隐式install | final-web.txt |
| 原基础宿主 | PASS，4/4 | infrastructure-tests.txt |
| 安全独立PG/KC集成 | PASS；最终完整14项，真实PG、PAR，0跳过 | final-security-complete.txt；强制integration CI |
| 五身份真实协议 | PASS，310检查；匿名/坏Cookie/回调/Forwarded/范围/角色/CSRF/双实例/注销重放 | SEC/oidc-par-third.json |
| 过期Cookie | PASS，实际200→只失效本测试行→同Cookie401 | SEC/expired-cookie-http.txt及完整套件 |
| UI与真实浏览器 | PASS，5项UI夹具、2项真实OIDC；安全负探针失败正确且无敏感产物 | FE/mobile-nav-ui.txt、final-browser-oidc.txt、FE/oidc-privacy-probe.txt |
| 实际OpenAPI对冻结合同 | PASS，路径/状态/媒体/DTO类型必需字段/错误/security/CSRF form/参数边界/operationId | openapi-runtime-final.json、openapi-contract-check.json |
| 同请求日志/Trace/指标 | PASS，含真实503错误Trace和实际YARP父子Span；Loki仅3索引，Prom两instance同时间54+4=58 | OBS/runtime/20261025T123735Z、trace-span-checks.json |
| 中文Grafana | PASS，4provisioned面板、3datasource health、2真实dataframes及4张安全截图 | grafana/、上述OBS runtime；无数据面板不伪造 |
| 告警 | PASS，inactive→pending→firing→inactive，安全停/续两个本树API | alert-drill.json |
| 7容器持久化 | PASS，旧Cookie两实例、PG审计、KC新登录、Tempo/Loki同Trace、Prom历史样本、Grafana新建状态保留 | persistence.json |
| 真正API进程替换 | PASS，内存旧Cookie跨新AppHost/双API；注销重放拒绝 | api-process-restart.json |
| 数据库故障 | PASS，依赖503/live200/ready503、同Cookie恢复；初客户端超时保留 | dependency-fault*.json/txt |
| 官方依赖审计 | PASS所选审计，无已知NuGet/npm漏洞；npm493图、已装390许可/159NuGet清单 | dependencies/ |
| 同Head Linux CI | 最终以manifest.runtimeCi实际run ID/head/conclusion为准；较早b57f6f3 run40180209973两job成功仅作里程碑 | CI记录、manifest；不拿旧run代替最终 |
| Windows原生/Intel Mac | NOT_RUN，无对应主机；三平台锁恢复PASS不代替宿主运行 | dependencies/*-locked.txt；开发手册 |
| 完整镜像CVE/SBOM/签名 | NOT_VERIFIED，摘要/官方来源/许可已核验，未调用收费或不明服务 | OBS/dependencies与dependencies/ |
| 生产证书轮换/SLO/RPO/完整合规 | NOT_RUN/后续专项；当前共享加密与重启PASS不等于生产验收 | 安全手册；不进G2 |

## 失败修复和独立审查

第一轮0Critical、3Important（指标writer合并、YARP查询log、pnpm隐式恢复）、1Minor移动隐藏导航均修复。第二轮0Critical、1Important为运行时OpenAPI漂移，已用实际Kestrel/完整语义对照修复；中文局部变量Minor已补。最终固定Head独立复审见review-final.md；不能把本报告当作Reviewer自签。

保留真实失败：Mac证书导入、保留路由、TS/ESLint peer、pnpm安装脚本、移动溢出/键盘、urllib PAR/Secure-localhost与Cache-Control假设、私有文件Path.open错误、Loki metadata误当索引、OpenAPI遗漏、导入顺序、数据库测试提前超时。修复测试本身的假设时未降低产品安全策略，PAR/Secure不禁用，未删业务断言。Grafana kiosk隐藏标题导致截图等待失败，改为认证后实际面板捕获。生产Host配置缺省/通配的真实RED→GREEN另由Master补齐。

自动审批曾拒绝Kiota非owned输出、OBS广泛敏感搜索和SEC修改共享Host，均采用owned evidence/进程注入/由Master写共享行的安全替代，无绕过，无剩余该类阻断。

## Git与复检

SEC最终分支cecf43b00f4f5f12c9309640d68ed665f2643498，FE ce28552c3feb839eb2d9b447b4f25975bd439244，OBS a52dc13c46abbc79776c86d4f8d4dcfa801cc99b，均Push且非忽略树干净。SEC同步Master公共提交的重复历史未再合；Master以bcd28ef→5e157df、cecf43b→174f2ca追踪cherry-pick，其余按可追踪merge。生产Host/最终文档由Master追加。main唯一集成责任人为Master，最终main与候选Head/CI见manifest及最终回执，不强推。M0树和历史状态保留。

运行栈验收后由唯一AppHost受控关闭；6个本轮命名卷保留，未prune或操作其他项目。私有配置/密钥仍在忽略且受限.tools目录，ZIP绝不包含。复跑见[操作手册](../../../development/wave2-local-development.md)。最后只有一个标准Review ZIP，完整Base..Head diff、源码/任务/ADR/原始脱敏证据、成员哈希和独立重开结果；交付后停止等待复审。

最后生产Host核查发现“需显式AllowedHosts”的既有说明尚未落实启动校验，Master新增真实构造RED，修复缺失/空/通配/无关host失败关闭；完整14/14 PG+Keycloak套件复验成功。该增量待最终独立源码复核。
