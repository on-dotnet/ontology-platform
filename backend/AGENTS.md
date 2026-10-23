# 后端工程规则

继承根AGENTS。`OntologyPlatform.slnx`仅非业务入口，当前无可构建项目，不以空solution构建表示后端通过。

## 架构与实现

- .NET10/ASP.NET Core10/EF Core10，英文微软命名；Modular Monolith + Vertical Slice，按复杂度DDD。Domain不依赖EF、HTTP、Jena或模型SDK。
- 模块独有DbContext、schema、迁移和写入合同；不跨模块改表，不共享巨型DbContext。应用层可直接使用本模块DbContext；显式映射或LINQ Projection，无AutoMapper和通用Repository/UoW。
- ServiceDefaults只放OTel、健康、发现、HTTP Resilience等启动扩展；BuildingBlocks不放共享业务实体或万能基类。REST/MCP/UI复用应用服务，公共合同单写者。
- API以后优先原生OpenAPI/ProblemDetails/IExceptionHandler/ILogger/System.Text.Json，ValidateOnStart、TimeProvider、HttpClientFactory、CancellationToken、RateLimiting；高性能日志LoggerMessage，性能结论需要真实测量。

## 中文文档与格式

- 所有手写class/interface/record/struct/enum及枚举成员、属性、字段、常量、构造函数、方法均有有意义中文XML Documentation；按语义提供summary/remarks/param/returns/exception，不能用模板复述名称。
- 每个手写局部变量在声明处用中文说明用途；核心算法解释业务依据、单位、时间、身份、幂等、事务一致性和错误恢复边界。
- 相邻成员/属性之间保留一空行；`///`文档紧贴对应Attribute组或声明，不插入破坏关联的空行。Allman、4空格、Nullable、Roslyn分析；生成文件明确豁免。
- CS1591仅检查编译器可覆盖的公开成员。私有成员、局部变量、中文质量和成员空行需专项工具/人工评审。本轮无C#源码，相关编译/格式检查NOT_RUN；不得宣称PowerShell静态检查覆盖注释语义。
