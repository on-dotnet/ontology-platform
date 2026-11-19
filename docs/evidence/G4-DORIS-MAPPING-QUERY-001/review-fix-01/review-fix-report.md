# G4-DORIS-MAPPING-QUERY-001 复审修复

复审起点为 `0c287e45e1c355a00cfd5403d6cb787026b127e1`。本轮产品与浏览器输入对应 `9780c8f91cd084c1df11c604186d22d7f08f3023`。实测提交和交付提交由最终验证及包外回执分别绑定。G4 总体 PARTIAL。

| 项目 | 新执行与结果 | 重开入口 |
|---|---|---|
| RF-01 / AC09 | 旧版本中真实 PUT 已成功。450 ms 调用期限已到，DELETE 仍在 454.1471 ms 获得独立有效令牌，499.3738 ms 才返回。修复后，工作与清理共享原绝对截止，同步等待底层结束，未确认图记录准确 IRI。8 个受控期限用例通过。正式查询用时 1173.75/1200 ms，正式取消 4961.85/5000 ms，两者都返回 semantic_timeout。服务端确认真实 PUT、SHACL、依赖连接关闭、槽位释放；临时图最终回读 404。 | [原实现首次见证](initial-publication.json) · [正式 HTTP 见证](originals/browser-s2-doris-root-deadline-1795080387779.json) · [新输入与原始双流](current-inputs.json) |
| E1 | 原主体授权过期、120 秒剩余期限不足、旧目录及旧激活分别在入口拒绝；健康状态放行。只读 FE 审计逐窗口计数，反例均零表变更和零固定业务 SELECT，同一审计器在压力对照看到两类操作。 | [真实命令与窗口](originals/e1-audit-5a77f112b7c34a65bd2778629e657535.json) · [反例和健康回执索引](current-inputs.json) |
| E2 | 首份代表原件提交后，生产 MemberPlan／MeasureOnly 在干净检出实测 6,745,958 字节。M5、Doris 的实际 plan 分发及重复载荷、映射缺失、篡改和超过 15 MiB 的限制均经过既有消费者。 | [早期计划](originals/early-plan.json) · [早期成员](originals/early-members.json) · [定向工程测试](originals/e2-production-tests.json) |
| E3 | 首份 219 字节无末尾 LF 的原件通过 publish 首次写入，再用 restore 按长度与 SHA-256 还原；有 LF 的普通 JSON 原样发布。PG 历史的 17 份原件按原 Git 字节重新核对。 | [首写、原始命令及双流](initial-publication.json) · [历史映射](../implementation-01/historical-byte-mapping.json) |

## 受影响的产品行为

新执行包括 4 项真实发布批次与 SHACL、2 项 PG 黄金用例、G3 共享五秒期限、正式 G2 同发布读取、HTTP／MCP／UI 和新的 AC06。构建、浏览器驱动、源端夹具、执行命令与双流逐项按输入散列核验。[输入及证据](current-inputs.json)

正式取消先提交，源端同一 QueryId 的两个实例共三个任务以取消结束。FE 终止上界 43.553542 ms，BE 全任务为零上界 29.351962 ms，分支 402.4627 ms，总请求 910.9836 ms。结果字节、读回执、成功审计均为零，取消审计恰一条。原产品执行记录 503 query_timeout 和 termination_unverified。旧统计视图在 252.873667 ms 仍为 0/1。本次判断依据为准确任务 Profile、完整管线采样和原生取消事件；旧 HEAP 唤醒推导对此次执行返回 NO_GO，原件保留。[逐任务直接重开](originals/ac06-direct-560f4b4f-64fd-45a5-83f0-97802e021aa8.json) · [非作者结论](non-author-product-review.json)

原 implementation-01 及其固定 HEAP 验收沿用原 Head。数值、NULL、ABA 和历史恢复见证保留原执行身份。此前 M5 工程整集进程超时 -9，同输入 122+11+1 覆盖 134 个唯一用例。本批只执行受影响路径。原生格式扫描基线与候选均 exit 2，既有诊断由 273 降至 271，本批变更行新增 0。CI 和其他平台 NOT_RUN。[格式对照](originals/native-format-scope.json)

最终压力夹具按准确键恢复至实体 1 行、目标 3 行，两表前后散列一致。早先内存拒绝及对照日志不可见的运行均保留。三次零在途回读后，FE、BE 和平台 PG 优雅退回 STOPPED_KEEP。PG 的 exec 通道返回 137，容器本身退出 0、无 OOM，原生日志确认干净关库。旧 14 个容器仍已退出，三个易失服务按原 ID 持卷运行。其持久保全与隔离恢复待另批集中裁决。[实测后态](closeout-members.json) · [保全与恢复卡](resource-retention.md)

工作流实测提交为 `544c134f2db913a5392605f53726ae67e7c4d72e`。10 个受影响门禁通过，其中 5 项重新执行，5 项重开既有执行原件；全部重新核验资格。产品定向重跑及原件身份见上表。[工作流回执](final/workflow-receipt.json) · [准确候选双人复审](final/candidate-reviews.json) · [schema 2 验证](final/validation.json)

四次中间正式浏览器失败按准确命令、退出码、双流、宿主及相关源端证据留存，重开见[失败原件索引](final/diagnostics/index.json)。
