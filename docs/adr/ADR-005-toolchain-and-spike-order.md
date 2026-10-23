# ADR-005：工具链策略与PoC顺序

状态：**ACCEPTED，仅选择原则与PoC顺序**；日期2026-10-23。不代表MSTest/MTP、Kiota或Hey API已兼容验证。

## 决定

后端测试优先验证MSTest + Microsoft.Testing.Platform；TypeScript客户端优先Kiota，并用Hey API对同一小样例比较OpenAPI/TanStack Query适配。验证空值、可选字段、枚举、ProblemDetails、取消和认证传递，记录生成差异及维护成本。无实际结果前不预装两套生成器、不创建业务SDK、不把选型称为完全兼容。

固定.NET10 SDK10.0.402，rollForward=disable、allowPrerelease=false；C#随SDK，不用latest。EF局部工具候选10.0.13，不调用全局9.0.7替代。SDK缺失时不OS安装，不通过降级目标制造PASS。Node固定24.22.1安全LTS补丁、pnpm11.28.8；不升级本机全局工具。

CPM集中未来项目PackageVersion，当前没有应用包，不伪造包锁。无前端源码和真实包依赖，Turbo仅保留任务配置，本轮不安装Turbo/Next/测试框架，不写空pnpm-lock。实际依赖恢复、哈希及锁图校验在相应获批任务执行。

## 备选、验证与触发

传统VSTest、其他生成器均不是默认；微软优先方案不满足样本时，凭许可/安全/兼容证据提出变更。MTP runner的global.json配置待实际测试验证后加入，不先承诺可运行。

本任务真实执行PowerShell静态门禁及隔离正反例，应用构建/测试/格式、局部工具恢复及SDK比较PoC均按证据标NOT_RUN/BLOCKED。后续源代码引入触发真实编译、测试和锁图门禁；ADR-002发布一致性及ADR-004持久调度保持未来PoC门禁，未实施。
