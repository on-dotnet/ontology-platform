# Readiness预算测试：根因与验证边界

## 输入与范围

Base `4d5709cc4c529ce3f91a4f9977b2ecbda56371ee`，分支 `codex/G2-READINESS-TEST`。Master报告真实Linux CI run `40279318064` 在相同Head的engineering job仅本例失败：约1.032s、queries=8断言通过而HTTP路径数量不足；governance-integration成功。本子任务未独立拉取CI日志，原始CI事实由Master保管，不能用本地结果替代最终同Head Linux CI。

仅修改一个测试文件。生产 `G2Readiness.CheckAsync` 启动整体2秒预算及其子数据库1秒预算；八个EF探针全部完成后才调用Jena与RustFS。`/health/ready` 真实端点把false转换为503。原夹具强制8×70ms数据库等待，留给首次EF模型/查询编译、JIT、连接入口的余量只有440ms；查询入口计数先自增，再可取消等待，所以queries=8也不能证明最后一个查询完成。

## 实测红/绿

- 原测试默认Mac arm64冷进程：PASS，queries=8/http=2/2071ms/503；见 `original-default-jit-pass.txt`。该环境未复现Linux的精确症状。
- 相同未修改测试，进程级 `DOTNET_TieredCompilation=0`：FAIL 1/1，约1.2s，实际queries=6而预期8；见 `red-cold-full-jit.txt`。完整首次JIT真实成本使同一数据库子预算提前取消；未注入额外人工延迟。它复现同一提前退出原因，计数6与Linux的8不同，不宣称完全相同环境。
- 修复后相同full-JIT命令：PASS 1/1，queries=8/http=2/2036ms/503/storageCancelled=True；见 `green-cold-full-jit.txt`。

命令分别为 `dotnet test --project backend/tests/OntologyPlatform.SecurityTests --filter 'FullyQualifiedName~G2ReadinessBudgetTests' --output Detailed` 与 `DOTNET_TieredCompilation=0 dotnet test --project backend/tests/OntologyPlatform.SecurityTests --no-build --no-restore --filter 'FullyQualifiedName~G2ReadinessBudgetTests' --output Detailed`。绿验证去掉 `--no-build` 以真实编译修复；使用 `--no-restore`。

## 修复与防回归

真实Kestrel/生产路由先执行一次不注入等待的请求，并断言200、8个EF探针入口及两个HTTP入口；随后清零计数、路径和取消状态，开启原有延迟后才启动秒表及新的请求。预热通过原生产1秒/2秒预算，无绕开或重试。生产Options克隆、DbContext和路由保持原实现；仅技术I/O入口为既有隔离夹具，不代表真实PG/Jena/RustFS业务验收。

测量期间仍为8×70ms + 2×850ms = 2260ms。全部原断言保留：503、8查询、精确两个HTTP路径、取消为真、1.5s ≤ elapsed < 4s。若在数据库后或各HTTP阶段重置2秒，2260ms串行操作可以全部完成并返回200，原503与取消断言会失败。此论证来自现有控制流与原固定等待；未修改生产实施mutation，也未新增无关测试。

## 工具和证据

SDK10.0.402，Mac arm64；真实受锁restore。新树首次SelfTest/native因缺隔离PyYAML及MTP输出尾空格失败，保留 `*-environment-red.txt`。Master明确批准ignored `.tools/pythonlibs`只读链接到主仓已有PyYAML6.0.3缓存，无新增依赖、全局配置或私有runtime读取。日志只统一LF/移除尾随空白以符合仓库静态格式，实际内容、失败与退出码不改写；后续命令先写/tmp，再规范化归档，避免正在写的日志被自身扫描。

生产文件摘要：`backend/src/Hosts/OntologyPlatform.Api/G2/G2Readiness.cs` SHA256 `6b6e6dc336192b6970ff56cb8d84a99e76e26af928f3a78ed5ca0aaa152b62f5`；`backend/src/Hosts/OntologyPlatform.Api/PlatformEndpoints.cs` SHA256 `bf951b51b3e0d004473035228a25b2fbc2ab1392108c69f17cb70c2d1aacecd4`。源配置/锁/CI diff为零。完整原始命令结论保存在同目录；仅格式检查workspace警告保留，不称无警告。

最终独立Review、Master集成、同Head Linux CI及唯一Review ZIP由Master负责，本分支不合并main。浏览器、生产、付费模型、真实PG注入验证本任务NOT_RUN。
