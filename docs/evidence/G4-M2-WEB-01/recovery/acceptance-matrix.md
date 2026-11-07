# 实际验收矩阵

任务 G4-M2-WEB-01；真实测试输入提交 `325bd87fe5e67fa8137176461800651de5bb1b08`。范围限已批准的合成固定 HTTPS GET、API_KEY_REF 和 WEB_API_KEY；不宣称支持任意公网 Web API。NONE、OAuth、分页、其他连接器及 M3/G6 暂缓。

| 项目 | 实际结果 | 原始证据 |
| --- | --- | --- |
| 两次幂等 prepare | DEPENDENCIES_READY；下载、restore、文件物化、旧凭据复制均 0 | environment/prepare-delivery-1.json、prepare-delivery-2.json |
| Connections 单元与分发 | 29 PASS，0 skip | local/unit-current.json + 原始日志 |
| 公共 wire 合同 | 16 PASS，0 skip | local/wire-current.json + 原始日志 |
| Connections UI | 119 PASS，0 skip | local/ui-current.json + 原始日志 |
| TypeScript / lint | 两项 exit 0 | local/typecheck-current.json、lint-current.json；零字节日志以无损 envelope 保存 |
| 真实 HTTPS / DNS | 12 + 1 PASS，0 skip | runs/m2-5e5a2f7a62de/fixture-receipt.json + 两份 MTP 日志 |
| PostgreSQL 原实现回归 | 1 PASS，0 skip；真实数据库及 VerifyFull 对照 | runs/m2-beb513edec23/pg-receipt.json + pg-test.log |
| 真实 OIDC/API/UI/HTTPS 闭环 | 19 PASS，0 skip | runs/m2-c72b9c07e76c/browser.json、receipt.json |
| 泄漏与审计 | 平台 dump、API/Web 日志扫描通过；11 类审计动作存在；原业务数据未归档 | 同一 smoke receipt |
| 资源清理 | 最终三 run 18 项准确资源删除后验通过；两个任务标签查询均无残留 | resource-closeout.json 及每 run resources/receipt |
| 按影响工程门禁 | 10 个受影响门禁 PASS；工程 18 / 环境 6 REUSED；任务准入 11 / shared smoke 14 FRESH；policy exit 0 | ../gates/ 下发布的最终回执 |
| 独立 Review | 无未关闭 P0/P1；证据及 ZIP 实际复核分别记录 | independent-review.md；ZIP 重开记录在包外回执 |

每组真实测试是在本任务中 FRESH 执行。随后产品门禁标记 REUSED，并 FRESH 重核原始 bytes/SHA、日志中的实际计数/exit、当前驱动及四类构建完整输出绑定、清理预期 ID；不依据 manifest 自报 PASS，不累加重叠门禁中的测试数。精确命令、退出码、时间及散列保存在原始 JSON；可机器读取的索引为 acceptance-matrix.json 和 product-proof-index.json。

19 组闭环包含真实登录/CSRF、用途冲突和双向 PG/Web 拒绝、非法认证/分页无 IO、Scope/Owner/Viewer 权限对照、UI 创建/Test/Enable/Discover/Disable、轮换与一次性引用、目标/范围变更拒绝、四类在途操作禁用取消、显式取消，以及自然等待 Intake TTL 后拒绝未绑定凭据且已绑定凭据仍有效。真实 socket 记录为 28 connections / 28 closed、5 aborted。

HTTPS/DNS 负例包括错误 SAN、非可信证书、重定向、JSON 超限/形态不符、取消与 DNS 混合/非允许地址拒绝；证书通过任务私有 CA、SAN/SNI 和 socket peer 核验，未关闭 TLS 校验。服务只暴露声明的逻辑 VIEW 与三字段，不持久化响应业务值。

GitHub CI、Windows、Intel Mac 均 NOT_RUN；无关 M1 全量验收 NOT_RUN / 本次不适用。长任务的锁屏/熄屏仅以本次有界 host monitor 为证，跨会话持续性 NOT_VERIFIED。历史失败和旧 P0 BLOCKED ZIP 保留，不参与当前 PASS 资格。资源与原用户文件的 KEEP 理由及解除条件见 resource-closeout.json。
