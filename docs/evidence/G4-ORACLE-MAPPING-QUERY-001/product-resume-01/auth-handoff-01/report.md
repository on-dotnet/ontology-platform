# Oracle认证交接与S1阻断交付

认证交接、提交后计时、同一浏览器连续执行及真实资格消费者已修正。两次实际窗口各 **1/4**：operator正常登录，auditor已提交但未通过。AC03-A、Mapping、S1及新reader恢复均NOT_RUN。第三次重试在资源前检阻断，浏览器没有启动。Oracle S0／AC03-B仍BLOCKED，cleanup250ms仍NOT_QUALIFIED，G4仍PARTIAL。

任务 `G4-ORACLE-MAPPING-QUERY-001`；产品Run `product-resume-01`；持久资源Run `implementation-01`。Base `33e66879a6b48e25580f1623316b88fe5a5e85cc`，分支 `codex/g4-oracle-mapping-query-001`；main固定 `5168f2c93ca226caa521a6dc4ac85439335274c4`。

## 输入与实现

真实两窗及首次62项回归绑定 `99235dba7353040531ee176b1dcef33147fcad73`；最终代码及最终62项回归绑定 `fdadc58f8be175090961c9fcee8af192cf6b790c`。最后两文件增量修字段级错误提示，并去掉测试对Git历史的依赖。最终代码没有再次进入真实认证窗口，不能把旧窗口认作新代码的成功实测。

表单可见可用、准确realm/form核实后才交接。人工时间独立计量；只观察同一认证POST元数据，不读取密码字段的值／长度、请求体或认证头。提交后40秒与人工绝对截止取较早者，回调、CSRF及正式/me共用剩余量。失败、取消、身份／角色不符、撤销或TTL不足阻止后续。

同一隔离Edge进程保存四个独立上下文，auth通过即进入A。恢复必须创建新reader上下文，核验实际新旧会话不同及真实票据，仅替换reader。Python外层、浏览器及实际command/mode资格消费者共同消费固定计划。每阶段保存原mode、输入、期限、窗口和散列，绑定真实父命令，不伪造子进程。

auth不读源、不续授或发布；恢复只读已存结果。原15项grant只在业务阶段按原四主体、连接、实体11字段重核，自然到期才同范围追加最长4小时，负例不自动修复。两窗均停在auth，未进入这些业务动作。backend/infra自Base未变化。

## 冻结计划

| 顺序 | 阶段 | 上限 |
| --- | --- | --- |
| 前处理 | 浏览器及身份绑定 | 60秒 |
| 1 | s0-oracle-auth | 四账号共用600秒 |
| 2 | s0-oracle-natural-cancel／AC03-A | 180秒 |
| 3 | mapping当前正式异人链核验／必要补齐 | 180秒 |
| 4 | s1 | 180秒 |
| 5 | reader-auth | 180秒 |
| 6 | s1-reopen | 180秒 |
| 后处理 | 浏览器关闭及报告绑定 | 60秒 |

父命令1620秒，无可选尾项。提交后最多40秒且不越过人工截止，产品阶段前必要会话与授权至少余210秒。产品5秒／源分支1秒／清理250ms保持。产品场景未执行，相关耗时为NOT_RUN，人工等待不计作产品耗时。

## 两次真实认证

以下均UTC，北京时间加8小时。机器回执完整列出安全结构化事实、真实exitCode、timingStatus、窗口、命令／双流散列；原始双流和浏览器原件留本机，经独立复核。

| 窗口 | 父命令 | auth准确审计窗口 | 结果 |
| --- | --- | --- | --- |
| 执行卡授权 | fd7186a07ec6438289856f8229aa85e7 | 12:46:19.253—12:47:55.463 | exit1／EXIT_FAILURE，1/4 |
| 用户明确“再来” | 2dfa6d5a8e2f443d9e0b3a4664870927 | 12:49:31.414—12:50:31.490 | exit1／EXIT_FAILURE，1/4 |

| 窗口／账号 | 可交互交接 | 首次提交 | 结束 | 人工ms | 提交后网络ms |
| --- | --- | --- | --- | --- | --- |
| 1 operator-ab | 12:46:20.379 | 12:46:51.096 | 12:46:51.758 | 30758.091 | 662.788 |
| 1 auditor-ab | 12:46:51.979 | 12:47:14.950 | 12:47:54.951 | 22985.025 | 40001.052 |
| 2 operator-ab | 12:49:31.735 | 12:49:40.581 | 12:49:40.794 | 8873.267 | 213.890 |
| 2 auditor-ab | 12:49:40.994 | 12:49:51.158 | 12:50:31.159 | 10169.811 | 40000.606 |

operator两次正式/me为同一原主体、platform.operator、site-a/site-b，登录审计另有两条allowed。operator-a／viewer-a未尝试，四真实票据资格未取得。auditor原件分类是ORACLE_LOGIN_SUBMITTED_TIMEOUT，停止在oidc_auditor-ab。网络栏包含当时漏识别错误后的等待，不证明IdP处理花了40秒。

auth独立源审计命令分别 `a51f02bbaa8943c59c92735a8daa1f2b`、`1916932ba02f400fafaf58fd56ef92cb`，准确窗口内固定业务SELECT各0；父命令完整窗口另审，各0；均无clientId过滤。没有执行A/S1/恢复，不创建虚假阶段或审计窗口。

## 凭据与过期诊断

用户本机页面显示auditor凭据拒绝。之后按用户要求，对准确已停止Keycloak实例只读过滤LOGIN_ERROR元数据，命令 `a2be6e708af54f678e99103cd1bfa8ee`：两窗内6条g2-auditor-ab／invalid_user_credentials。只输出时间、账号、允许的错误类别，不保存原日志。

这证明提交的凭据未被接受；**密码是否过期仍NOT_VERIFIED**，不能推断其他未尝试账号。原分类器只检查首个固定选择器，漏掉带字段后缀的错误或前方空反馈；最终修复枚举允许的提示节点并返回固定拒绝类别。两窗旧timeout原件保留，新诊断单列。未重置、读取或导出密码；公开文件不含附件、聊天凭据或认证载荷。

## 第三窗前检与资源

用户确认本机auditor条目并授权前检通过后再试一次，另明确批准仅恢复原三个Doris持卷实例。Docker恢复后，原3项由running变为exited；准确ID、镜像、配额、挂载仍一致。RustFS `57ef8d99c6eb37eb4681f9ae707537de93b556218394ad54c8703b2f2b2f5ce9`、Keycloak `3f1502f453da342d8cd57ab6514852d1fa06007baad709156abb7da0e5e2647f`、Fuseki `d3f2a4b9dd9d06bf3141e35c80b4c96246b47cc81092762f88171bf57dff5e04`已逐个恢复。5条真实命令与前后核对证明20项保护清单逐字匹配原前态：3 running、17 exited。

13:08:17的startup-03在产品服务启动前因RECOVERY_HOST_MEASUREMENT阻断。临时计量检出缺失，随后按原准确提交 `7d113e3ca9e6dc1b91722fe320c429ae1ace0cce`建立新的detached源码检出，10份公开原件经原解码器按旧SHA无损恢复。2份未公开FailureState无法恢复，未伪造。新检出实测761332KiB并重新计量，不冒充历史目录持续存在；因当前核算仍引用它，KEEP至引用正式退休。其他已缺失/tmp树保留登记，不全局prune。

13:10:41的startup-03b再次在服务启动前被ARCHIVE_LEDGER_OWNER阻断。仅stat诊断：6份账本归档device从16777229变16777234，inode、大小、ctime、所有权和私有权限一致。未读取归档内容，未核实当前内容SHA；这不证明内容损坏。旧账本未改，门禁未放宽。**第三次浏览器及人工窗口NOT_RUN**，产品副本和API未启动。

## 验证与历史资格

FRESH：最终注册入口 `python3 -B scripts/tests/WorkflowOracle.Tests.py`，命令 `7761358b693e4c79a2cfc889799de593`，62项／exit0／无skip；覆盖超过40秒人工等待、提交后期限、CSRF/me共用剩余预算、实际驱动连续A/S1与新reader、外层计划与真实资格消费者反例。非作者从仓库外实跑两Node文件21/21／exit0，发现并关闭测试依赖固定Git历史的问题。

REUSED：API、QueryTests、AgentTests输入／输出与既有有效构建相符；真实PG8/8仍归原命令 `92cd82b7d50d4b8ab7bd86026c4c724c`。R1/R2/R3按输入复用；本批启动曾核当前Fuseki两类全库和两发布图摘要一致，不重复旧数据恢复。prepare零下载，21项目／179包。

旧62项命令 `d8b3728b5fe94b48af83ee44ac1977ab`与两窗归99235dba。旧输入成功消费者拒绝OMQ_RESUME_NORMAL_OIDC；最终fixture改变后，当前消费者先拒绝OMQ_BROWSER_DRIVER_CHANGED。可核失败原件不等于当前成功资格。通用Oracle verify旧缺口OMQ_ORIGINALS_NOT_RUN_admission保持；完整SelfTest、CI及其他宿主平台NOT_RUN。

历史三窗 `ae2ebad4418249cc99d97f722b4d340c`、`3b9131ecad82459e88b9f2660b285def`、`f2dab63d98bf42fd97f19d3a2dde66c4`的0/4及独立operator历史1/1保留。19:20来不及提交来自用户反馈；19:27只知未到/me，不追写为密码错误。旧完整文件保留在Base的entry-fix-01。

## 收尾与交付

两窗关闭操作 `763de90e6d7f4ef8b0395101da137268`前后两次各7项排空计数全0；两准确API经TERM／退出／移除后验；5个持久替代实例退出保留。Fuseki为PROCESS_EXITED、cleanShutdown UNKNOWN，不要求锁文件消失。原卷／密钥／九份封存归档保持，维护CANCELLED/fence2行不操作。

最终准确ID只读核对：保护3 running／17 exited；任务5个持久副本exited；前两窗API不存在。当前启动准入仍BLOCKED，早先closeout PASS不替代新准入。宿主监测40次心跳、392724ms，策略持续READY；熄屏／锁屏连续性NOT_VERIFIED。四个原Finder未跟踪文件保留且不提交。

自动审批拒绝了广泛嵌入原始双流的公开候选，未执行该操作；交付改用字段白名单、准确散列和独立原件复核。三份文件提供完整本批结论及安全机器事实，私有原件保留。按用户例外不生成中间PARTIAL ZIP。普通push并回读，以最终准确Head链接交付；后续文档提交不冒充产品实测。main不变，停止在ChatGPT复审。
