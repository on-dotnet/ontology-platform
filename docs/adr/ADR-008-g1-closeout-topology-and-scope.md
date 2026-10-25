# ADR-008 G1收口审计范围与部署边界

状态：审计范围 IMPLEMENTED / VALIDATED_LOCAL；生产拓扑 PROPOSED，未授权实施。2026-10-25。依据G1-CLOSE-001，不调整原架构/依赖。

## 审计事实

旧SiteId单值无法表达多个授权厂区，取第一条claims造成不准确归属。选同表nullable text[] ScopeSiteIds，避免新业务表/字符串拼接；null历史未知、[]明确无厂、单厂[a]、多厂[a,b]。新写入来自可信scope，SiteId仅单厂兼容。读取要求非空组织匹配且非空数组全部属于当前sites；legacy/空scope默认隐藏，保留存储事实，禁止猜测回填。全厂审计不是任一单厂权限的并集可见性：调用者须覆盖事件的完整范围。

读审计顺序：鉴权→校验→PG查询物化→提交唯一成功审计→响应。本请求不含自身；其他请求是否可见取决于其提交和当前查询快照。失败无200/无成功AuditId；不递归读写。数据库持久事实可追踪，不宣称已实现对PG超级用户的防篡改、数字签名或外部WORM；生产不可否认/保留策略待G8。

迁移不改旧行，允许无结构化事实时安全Down；一旦含任意非null范围（包括[]），Down显式拒绝，使用经过验证的快照恢复或前向修复，不能drop列丢事实。

## 当前开发拓扑

API Web:Origin仅回环HTTP，Next内部SSR PLATFORM_API_ORIGIN固定可信回环API，适用同机隔离开发。双API共享PG和加密keyring实测不等同HA生产部署。不能把回环地址用于跨主机/容器Next，也不能仅把IsLoopback去掉作为生产支持。

未来部署ADR须经新授权：确定API→Next和Next→API的独立可信origin/HTTPS/mTLS或受限内部网络、DNS服务发现/代理Host、SSR Cookie固定上游转发与SSRF拒绝、部署边界/探针/证书密钥环/会话存储/滚动更新；按实际跨主机容器拓扑复验登录退出、CSRF、转发头、双实例、错误脱敏/Span、依赖故障与恢复。G8批准SLO/RPO/RTO与安全入口后才可称HA。当前无生产配置源码变更。
