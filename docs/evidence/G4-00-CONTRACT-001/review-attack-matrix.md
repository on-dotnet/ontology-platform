# 非作者 Reviewer 攻击型反例

来源：/root/g4_contract_review 首轮只读报告，由Master原意归档。GPT-6.1 Sol/high派发。覆盖表示书面规则可追溯，除Schema/语义合成fixtures外均产品执行NOT_RUN。

| ID | 反例 | 预期设计行为 |
|---|---|---|
| T01 | scopeSelection扩大厂区 | 403；server Actor与完整scope交集 |
| T02 | 请求未授权字段 | 拒绝或合法PARTIAL，无越权值 |
| T03 | 副作用SELECT/CTE写/多语句 | 编译器拒绝+源最小权限 |
| T04 | 对象名SQL拼接 | 登记objectRef/安全identifier拒绝 |
| T05 | DNS重绑/IPv4映射IPv6 | socket前目标核验 |
| T06 | 302/next/OAuth跳IMDS | 逐跳重新授权 |
| T07 | remote ref/恶意proxy | 不获取未批目标 |
| T08 | 同厂同号两个IRI | RQ-01选择IRI并当前ACL/版本重验 |
| T09 | 候选少于2/证据ID失联 | Schema/语义拒绝 |
| T10 | TD精度/未知时区单位 | 阻断或明确降级 |
| T11 | Oracle alias/Wallet额外字段 | strict拒绝；高级字段另批 |
| T12 | 普通MySQL冒充Doris/decimal越界 | 能力/类型检测拒绝 |
| T13 | secret配置改变沿用probe | 409重测 |
| T14 | TD双ref/NONE非null | 原R09..12拒绝 |
| T15 | Secret/SQL/internalURL泄漏 | 日志和响应脱敏 |
| T16 | 旧revision/同key异payload | 409 |
| T17 | 作者双角色自批/过期 | 403/409；X03 |
| T18 | 审批后schema/secret/权限漂移 | 旧active不变 |
| T19 | CAS审计Outbox故障/双激活 | 同事务回滚/单成功 |
| T20 | 回滚跨scope/换manifest | 拒绝；RM-02机器载荷实施前另冻 |
| T21 | 为snapshot字段查询越权ID | RQ-03 ProblemDetails，不读snapshot |
| T22 | 旧Run撤权/游标过期 | 当前ACL403/cursor409 |
| T23 | 取消断线再试/重复取消 | 幂等终态，禁止无界重启 |
| T24 | 成功+超时+拒绝 | 仅合法PARTIAL或UNAVAILABLE |
| T25 | 注释提示注入/自主发布 | 模型OFF/外联策略/人工审批 |
| T26 | 清旧树卷/全局prune | 白名单拒绝，不触旧资源 |
