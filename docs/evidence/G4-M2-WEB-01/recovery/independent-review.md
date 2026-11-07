# 非作者独立 Review

Reviewer：只读子代理 `/root/p0_review`。以下由 Master 保存其独立输出；Reviewer 未编写实现、未操作测试资源。

代码审查基线：`b3b68500d76ab5965fcc540afb883ca605cb15dd`；候选：`325bd87fe5e67fa8137176461800651de5bb1b08`。

结论：当前未发现未关闭的 P0/P1。独立 diff-check exit 0。公共行为变化限于后续批准的 `WEB_API_KEY`，未涉及依赖锁、CI 配置、数据库迁移或其他连接器实现。

已提出并闭合：

- 离线 Web 缓存不得夹带未核验文件；依赖链接必须匹配锁定依赖图，不能只证明目标包本身合法。
- 先审 PG/Web 公共分发和用途合同，再允许 Web 实现；增加禁止旧凭据换目标的测试。
- 保存后 Test、Enable、Catalog 的在途源 IO 增加状态/版本/会话取消；JSON 校验观察取消。
- TLS 错误 SAN 实测暴露会话恢复；关闭 TLS 恢复后真实 12 HTTPS + 1 DNS 用例通过。
- 驱动必须使用服务器完整 ETag；并发拒绝按 Test/Enable/Catalog 各自准确结果断言。
- 测试程序集必须绑定当前源码与完整输出闭包；不能仅凭 DLL 存在。
- 清理前先写 NOT_VERIFIED，预期准确 ID 清单全部完成后验才可 PASS；网络名称/ID 比较纠正。
- 原件资格重核不能信清单自报测试数/exitCode；必须解析原始回执、日志、运行时绑定、清理证据。
- M2 产品门禁不得通过通用 load_reuse 捷径跳过资格重核；驱动变化必须参与产品 inputs 选择。Reviewer 独立运行选择回归 1 test PASS、exit 0。
- Scope 对照改用有读权限的 operator-a，并同时验证允许范围成功；自然过期等待两份凭据的最大到期时刻。

Reviewer 已独立读取历史 15 组 smoke 和 13 例 fixture 成功原件；这些历史结果不替代当前完整候选资格。最终自然 TTL、最终输入绑定及 ZIP 独立重开见本文件后续追加实证结论，未取得前不宣告任务完成。

## 最终真实原件独立复核

Reviewer 后续只读断言 exit 0：m2-c72b9c07e76c 的 browser SHA、准确 19 组 / 0 skip、当前 driver/API/Web 构建绑定及 10 项清理 ID 一致；11 类审计和泄漏扫描通过。m2-5e5a2f7a62de 原始两日志 SHA 与 MTP summary 12+1=13 / 0 skip / exit 0、当前 driver/Connections 绑定及 4 项清理 ID 一致。Reviewer 未重跑设施。PG、最终 workflow 和 ZIP 重开另行核验。

PG m2-beb513edec23 独立核验 exit 0：1 PASS / 0 skip、原始日志与当前 driver/build 绑定一致、4/4 清理闭合。三组最终运行矩阵准确。原彩色 UI 日志虽然 119 PASS，但资格解析 VITEST_SUMMARY 失败；该失败保留于 gates/b2dbf5fac9fe4140be3121c2bb064ac0，原日志及回执复制到 history/ui-colored-original。Master 仅重跑无色 UI 单元 119 PASS，未改任何冻结驱动或产品代码。

无色 UI 原件后续独立复核 exit 0：119 PASS、receipt/log SHA 和当前 Web 构建绑定一致；独立 diff-check exit 0。Reviewer 已读取 22 个转换缓存文件的精确清理记录，未操作资源。最终 workflow run 6693bea5415c4181b19a9979e1dbc06d 全部 10 个受影响门禁 PASS，等待 Reviewer 对该最后回执独立复核。

## 最终门禁与证据格式复核

Reviewer 独立核对最终 10 门禁的发布日志 SHA、exit/status；工程 18、环境 6 从指定提交提取原 JSON/日志并验证实际 summary，检查 exit 0。当前无未关闭代码 P0/P1。最终 Git 全差异检查发现批准文档尾空格和 UI 日志额外 EOF 空行；依 Reviewer 建议，原始字节保留于无损 envelope，当前 UI display transcript 仅去除额外末尾 LF，原 command/exitCode/timing 不变，不称为新 Run。原批准文档 SHA 以 recovery/p0-approval-original.json 中完整原 bytes 为准，MD 为排版规范化显示副本。最终转换关系和 ZIP 重开另有独立实证。

## 最终可归档结论

Reviewer 独立断言 exit 0：批准 envelope 解码 bytes 与 Downloads 原批准附件完全一致，SHA256 `89b6a38e17e5af611824e8851c2d814f496bbc7a334fe470a40dbf618f283e9c`；UI raw bytes 与 6640341f 父提交原 log 一致，display 精确等于 raw.rstrip(LF)+LF；批准显示副本仅去除行尾 space/tab。当前 Base..HEAD diff-check exit 0；display-qualification 五门禁 PASS，REUSED 标识正确。无未关闭 P0/P1。源码及实际验收 Review 通过；唯一最终 ZIP 的独立 VerifyOnly 和 SHA/Head 核对结果写入包外回执，避免修改包内内容形成循环。

## V3 路径适配独立复核

Reviewer 审实际 diff：仅资格器精确自身历史散列排除及原日志后缀读取；其余执行驱动键集合/值完全相等。专项 RED 两个真实失败、GREEN 13 项通过；覆盖七个驱动逐一修改/缺失、未知键、原日志 SHA 篡改和双路径歧义拒绝。独立脚本 exit 0，核对 39 项 MOVE 的新 bytes 与当时 HEAD 原 bytes 相等、SHA 一致且旧路径缺席；三份真实设施 receipt bytes 完全未改。新资格器重核 HTTPS 13 / PG 1 / smoke 19 及当前构建 PASS。无新增 P0/P1，允许进入当前资格候选按影响验收；真实产品执行结果仍为 325bd87f 上的 REUSED。

归档适配后的最终按影响执行 run `488e2b43700f446398efccbfa0ba2c52`：10 门禁 PASS；资格/专项实际测试提交 `761e961dd06d020ff75c175134a1ec25f7a671b7`。13 项准入 FRESH，工程18/环境6/shared smoke14 经原提交核验 REUSED，五产品门禁 FRESH 资格复核 / REUSED 实际产品执行。最终交付提交仅增补文档，source 输入以该 TestedCommit 绑定；独立 ZIP 重开追加结论保存在包外回执。
