# ADR-009 G2语义、发布与执行一致性

状态：ACCEPTED_WITHIN_G2（契约独立审查至2ac9ec4全部关闭）；2026-10-26。对应用户明确授权G2-THIN-SLICE-001与精确依赖批准，非架构扩展/生产授权。

## 决定与备选

1. 复用现有Jena6.2.0同进程内存验证dataset及TDB2正式版本dataset，启用官方fuseki:shacl；真实PoC已验证，无新增Java服务/SDK。独立Java验证进程会引入新架构与部署，当前无必要。普通SPARQL不能冒充SHACL。原始UTF8源保留PG/不可变RustFS，TDB2规范化不能改写源事实；复杂公理不能可靠编辑则保留/只读/阻发布。
2. 发布采用已批准不可变外部制品、隔离图、回读/SHACL/query验证、短PG CAS+audit+Outbox、调和。PG与Jena/S3没有跨服务ACID；不采用先改active后异步部署。超出G2的分布式事务、消息产品/新图库不引入。
3. 同一PG数据库可显式共享物理连接/DbTransaction，但每模块自己写自己的表。Governance自有enlisted writer，Ontology自有修订锁读取，Publishing协调并只写自己active/Outbox；用EF官方cross-context transaction。既有API AuditService独立SaveChanges不能证明发布同事务。选择原子Governance审计而非未经说明的异步治理projection。
4. 合同仅唯一无外部包DTO项目，真实多模块消费者共享；Domain独立纯净，不建第二套Evidence/Run/泛型Result。Query Gateway能力白名单与所有传输共享；Run固定完整snapshot和PG事件，MAF不替代确定性发布/网关/事务。
5. 用户2026-10-26精确批准Monaco0.57.0、Cytoscape3.34.4、MCP.AspNetCore2.3.0、MAF1.26.0/Extensions.AI10.11.0及安全许可核实的必要传递闭包；不自动扩展其他MAF直接包，不用preview/收费/云。SSR客户端懒加载，390同草稿原生编辑fallback。

## 证据与后果

具体字段、状态、预算、路由、权限与Task DAG以[唯一G2合同](../contracts/g2-thin-slice-contracts.md)为准。Jena实测见本轮master/jena-shacl-poc-green.json；首轮客户端415失败原样保留，9项通过不等完整业务PASS。接口/事务/预算/恢复仍需S1/S2/S3真实验证与独立Review。

官方依据：[Jena端点](https://jena.apache.org/documentation/fuseki2/fuseki-config-endpoint.html)、[6.2.0 SHACL实现](https://raw.githubusercontent.com/apache/jena/jena-6.2.0/jena-fuseki2/jena-fuseki-core/src/main/java/org/apache/jena/fuseki/servlets/SHACL_Validation.java)、[TDB字面量](https://jena.apache.org/documentation/tdb/architecture.html#inline-values)、[EF共享事务](https://learn.microsoft.com/en-us/ef/core/saving/transactions#cross-context-transaction)、[.NET原生SSE](https://learn.microsoft.com/en-us/aspnet/core/fundamentals/minimal-apis/responses?view=aspnetcore-10.0)。官方来源支持可行性，不替代运行验收。
