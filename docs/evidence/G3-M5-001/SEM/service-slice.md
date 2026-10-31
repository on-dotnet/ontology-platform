# M5固定版本只读服务回归切片

Owner仍仅SEM约定文件，父产品修复45cbb8d。新增G3M5ServiceTests：10项无需服务的实际应用守卫已通过，0失败0跳过，构建0警告0错误；角色/身份、固定版本判别、修订、未知枚举、正式读取能力缺失均在SQL/RIOT前拒绝。测试构造不可意外长连接的PG上下文，但不使用Mock代替产品验收。

四项真实PG/RIOT方法已编译，等待Master同一隔离harness统一执行，不在此预填PASS：

- 原文含BOM/CRLF/注释的创建及连续只读；源JSON、历史投影、hash、revision、command与业务审计前后不变，UTF8字节相等。
- 固定旧修订不被当前头替代；权威源导出重入仍准确hash，显式blank重命名由真实有界图同构判定；基本结构编辑复杂图仍被拒绝。
- 跨组织/缺厂/无角色在首RIOT请求前拒绝，合法完整scope viewer可读；缺历史修订404。
- 本测试临时资产存储hash被篡改时503且RIOT请求数0，finally恢复原字段。

实际入口：本轮Master准备真实Jena/PG并执行semantic-roundtrip.py --postgres --filter 'FullyQualifiedName~G3M5'。仅短守卫命令为dotnet test --project backend/tests/OntologyPlatform.SemanticTests --no-build --no-restore -- --filter 'FullyQualifiedName~G3M5ServiceTests.Guard'。未创建容器，未新增依赖，未改合同/路由/DI/profile或其他树。
