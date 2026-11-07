# G4-M2-WEB-01 恢复实施说明

基线 `b3b68500d76ab5965fcc540afb883ca605cb15dd`。独立任务分支与 Worktree 沿用原任务，未更新 main。原 P0 BLOCKED ZIP 原字节保留；本目录属于后续明确批准的恢复实施，不能反向改变旧证据结论。

| 边界 | 原批准 / 后续裁决 | 本轮实现 |
|---|---|---|
| 公共凭据用途 | 后续明确增加 `WEB_API_KEY` | 只扩展既有字符串校验；DTO 字段、16 路由不变 |
| Web 认证 | `API_KEY_REF-only` | 服务端固定 `X-Fixture-Api-Key`，跨 PG/Web 用途隔离 |
| NONE | deferred | 可解析、不可执行，不新增 sentinel 或 nullable 存储 |
| OAuth | deferred | 可解析、运行前拒绝 |
| 分页 | deferred | 仅 `NONE`；PAGE/OFFSET/CURSOR/LINK 在凭据消费和网络前拒绝 |
| 目标 | 单一合成注册 | `https://web-source:8443/v1/items`、`fixture-items`、org-demo/site-a；旧 Key 不允许换目标 |
| 其他连接器 | 不开发 | PG 原实现保留；Oracle/Doris/TDengine 不启用 |

公共分发保留原 typed PG 接口，增加 typed Web 接口。用途从服务器验证后的配置决定，Intake 重放、一次性绑定、已绑定秘密读取、轮换及生命周期路径共同复核。保存连接的 Test/Enable/Catalog 与后台作业都观察状态/版本/会话变化，取消传至实际驱动；没有跨源 IO 的长数据库事务。

Web 使用完整 DNS 集合筛查与准确 socket IP 绑定，合成例外仅允许 172.30.240.10。禁代理、Cookie、重定向及 TLS 会话恢复；每次正常校验任务 CA、SAN/SNI。每次请求独立 handler、HTTP/1.1、固定 GET。网络子期限 3 秒，Probe 总期限 10 秒，Discover 20 秒，响应上限 2 MiB、深度 16、最多 1,000 条合成记录。

目录来自服务器登记的固定 JSON 合同，不从样本猜测精度：一个逻辑 VIEW、三个字段。大整数以原始词法校验，原始行值不保存；missing、null、重复字段及不完整响应严格区分，错误不能伪装成空目录。合法空数组仍对应已登记视图，不宣称 EMPTY_VERIFIED。

Web UI 复用原页面：用途随类型/执行模式选择；类型、目标参数或范围变化清除临时凭据引用。未实现模式明确不可测试或保存。没有改菜单、Design System、权限、数据库迁移、依赖或锁文件。

环境采用现有工具及内容核验后的离线缓存。完整包成员、pnpm workspace/shim/依赖图及当前工作树绑定均复核；不复制旧 runtime/凭据。最终两次 prepare 原件位于 environment，均为零下载、零物化、零 restore。测试生成缓存保存在 ignored 目录，原始日志按 archive-map 移动一次；需保留 CR、尾随空格或空输出的日志以 raw-log-envelopes 可逆还原，不改失败原字节。

验收严格区分真实执行与资格重核：workflow 产品门禁每次解析原始回执和日志，验证成功数/skip、真实退出码、原运行构建与驱动输入、资源清理后验。产品结果复用记 REUSED，当前资格检查记 FRESH；驱动单文件变化也激活产品门禁。未重复 M1 全量验收，未把结构 READY、容器启动或未运行的平台当 PASS。

交付预检识别 V3 禁止 `.log` 路径，原始测试日志以相同 bytes/SHA 移动至 `.txt`。唯一资格解析器增加归档后缀兼容；历史执行输入比对仅排除该解析器自身，当前资格逻辑仍由 workflow 输入及专项拒绝测试绑定。其余执行驱动、产品源码、构建输出和真实运行回执不变；复用与当前资格执行分别记录。
