# G4-M5-INTEGRATION-001｜工程入口收敛与PG整合

## 当前执行与授权
唯一执行状态：FINALIZING；产品与受影响工程验收PASS；batchAcceptance待包外最终回执闭合BI-11；G4Overall=PARTIAL。最终复审关口为ChatGPT，不更新main。

人类已批准[一次性A/B/C批次](../evidence/G4-M5-INTEGRATION-001/authorization.md)，以及[精确M3暂停和M4双网络拓扑](../evidence/G4-M5-INTEGRATION-001/additional-authorization.json)。没有普通helper、修复、构包待批事项。

- Base：`a6716b11c3795e5670c07f1ca37057e5649bed89`；分支`codex/g4-m5-integration-001`；一次创建并持续复用独立托管树。
- PG与完整工程SelfTest资格TestedCommit：`4e20be50c1023b9bcd9f97e02dac92e35f20d130`；后续M5构包消费者候选`ef04666cd4a52495014da51b4600215b75e0eaac`，其受影响构包/工程验收单列；PG资格按实际输入重开。
- Master唯一作者；Explorer与Reviewer只读，非作者审查消息由Master如实转录，独立执行身份不伪造。
- owned_paths：本任务卡/证据、当前授权/规划/Web规则、workflow/context/M5薄消费者及直接相关PG/环境/缓存/前置检查helper，verify/structured-validator/gate登记及直接回归，三个既有C#测试的M5身份/前置检查。最终邻接修复包括StructuredFiles.Tests.ps1预期负例输出标记。
- read_only_dependencies：冻结M3/M4产品合同/实现、历史证据/ZIP、其它KEEP；无产品DTO/持久语义/权限/5秒预算变化。

## Specify / Verify
唯一验收矩阵：[acceptance.json](../evidence/G4-M5-INTEGRATION-001/acceptance.json)；当前机器证据：[validation.json](../evidence/G4-M5-INTEGRATION-001/validation.json)；全部原件路径/散列/封装恢复：[originals-index](../evidence/G4-M5-INTEGRATION-001/integration-01/originals-index.json)。BI-11必须在实际构包、普通push和非作者同包重开后由包外回执关闭，不能预先宣称通过。

| 要求 | 当前结果与边界 |
|---|---|
| BI-01/02 | 当前授权/规划/Web事实收敛，历史原文固定blob可恢复，五源及平台缺口保留 |
| BI-03/04 | 代码/证据上下文分开，机器diff选择；未知路径拒绝，执行依赖显式登记 |
| BI-05 | numeric独立SQL仅targets1/2，NULL/1.010不成边；ABA同query源读后B→A并在1004.5732ms提交拒绝；三个单元变异被杀死，不冒充DB变异 |
| BI-06/07 | 真实失效session、disabled连接、未监听Web、旧activation均短拒绝；错库/真实他任务Owner在SQL前拒绝；只读快照与独立测试库保留 |
| BI-08/09 | 任务自有正式G3→TLS只读PG/目录→Mapping异人审核激活→Gateway/UI/MCP；新OIDC及API重启恢复原canonical，源扫描129/61保持；撤权/并发/容量/取消/秘密轮换/禁用及真实MAF/ABA原件有效 |
| BI-10 | 非作者独立预期、原件SHA与语义审查；资源P2、目录前提、当前新增格式及汇总输出发现关闭 |
| BI-11 | 唯一V3及非作者同包VerifyOnly和包外JSON在最后交付步骤实测，不递归重写旧ZIP |
| BI-12 | 区间并集/失败/重测/构建/路径规模均留原件；实际模型活跃时间与未完整观测项UNKNOWN |

## 失败、限制与恢复
本轮所有旧失败保留。初次MAF超时不算保护通过；numeric NULL先于Mapping的错误准备顺序已改为正式激活后添NULL；grant过期保留精确续期审计；numeric建表使旧全目录失效后通过正式发现/新映射恢复。旧realm discovery404原因未建立，旧私有材料保留。s2-race前置窗口失败经独立短定位与一次有界复验，不改产品5秒。

原生format真实exit2，三文件52项全部继承Base，本轮新增0；不宣称全量format通过。完整SelfTest的预期子失败输出误判已通过精确exit/拒绝文本标记修复，通用FAIL/ERROR解析不放宽；未登记测试被计划拒绝后已显式登记并验收。

M5运行7容器、6GiB/4.5CPU；含M4共同12GiB/9CPU；最终实测明细与宿主RSS见资源原件。M5服务/卷/私有runtime/快照KEEP至复审后精确授权回收；临时独立测试容器已按白名单删除并后验。仅授权M3六容器暂停，卷/数据保留；其它KEEP不动。bridge有出站能力，不声明网络层断网。宿主策略/600秒监控有原件，锁屏/熄屏实测NOT_VERIFIED；早期进程名筛选漏掉改名Next的RSS不能当完整0，最终以cwd+后代实测纠正。

本轮仅PG整合切片；五源冶金、非PG映射查询、双架构、CI及生产未验收；TDengine WAIT_FOR_EXTERNAL_INPUT。零新增下载/依赖/费用；不更新main、不生产、不进入G5/G6/G7。

恢复从本卡、当前授权、acceptance/validation与最终包外回执开始；不要重载历史会话或重跑无关M1–M4全链。包外回执记录最终Head、普通push读回、唯一ZIP的大小/SHA及非作者重开，作为本卡FINALIZING到交付状态的唯一最终观测。

构包成员计划实测默认重复payload+diff超过15MiB；依附件第10节接入既有V3机制，归档分组package-final-01不改变执行RunId integration-01。所有本任务非PNG原件必须入包，唯一可索引恢复的是精确UUID命名的历史累计save(state)副本；全量文件名/内容哈希闭包扫描保留standard-907aa290真实引用，其余237份仍在Git且已逐字节核验。当前命令、报告、失败、反例、资格和最终四场景文件均随包，15MiB不放宽。

最终构包增量按影响验收通过，当前统一结果`f3ddedfe750f4199b0615ebf19426651`：engineering/package/policy实际成功；原PG五层再次只读重开全部PASS。完整SelfTest 486项发生在4e20，之后仅构包消费者/证据登记由当前受影响门禁覆盖，不把旧full输入冒称完全相同。
