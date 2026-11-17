# G4-M5-INTEGRATION-001｜工程入口收敛与PG整合

## 当前执行与授权
唯一执行状态：EF01_REVIEW_HANDOFF；工程验证已完成，最终Git/ZIP交付后验以entry-fix-02包外机器回执为准。前轮工程增量f620已交付，现按entry-fix-02追加授权修复早期量包逻辑映射去重兼容；main保持已审b5e3，G4Overall=PARTIAL，最终停ChatGPT复审。

人类已批准[一次性A/B/C批次](../evidence/G4-M5-INTEGRATION-001/authorization.md)，以及[精确M3暂停和M4双网络拓扑](../evidence/G4-M5-INTEGRATION-001/additional-authorization.json)。没有普通helper、修复、构包待批事项。

- Base：`a6716b11c3795e5670c07f1ca37057e5649bed89`；分支`codex/g4-m5-integration-001`；一次创建并持续复用独立托管树。
- PG与完整工程SelfTest资格TestedCommit：`4e20be50c1023b9bcd9f97e02dac92e35f20d130`；后续M5构包消费者候选`ef04666cd4a52495014da51b4600215b75e0eaac`，其受影响构包/工程验收单列，后续精确旧PASS包装策略候选`6453f8b1455430fce91eedec16a3496bcaf45ddc`；PG资格按实际输入重开。
- Master唯一作者；Explorer与Reviewer只读，非作者审查消息由Master如实转录，独立执行身份不伪造。
- owned_paths：本任务卡/证据、当前授权/规划/Web规则、workflow/context/M5薄消费者及直接相关PG/环境/缓存/前置检查helper，verify/structured-validator/gate登记及直接回归、`scripts/create-review-package.ps1`与`scripts/tests/ReviewPackage.Tests.ps1`，三个既有C#测试的M5身份/前置检查。最终邻接修复包括StructuredFiles.Tests.ps1预期负例输出标记。
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

构包成员计划实测默认重复payload+diff超过15MiB；依附件第10节接入既有V3机制，归档分组package-final-01不改变执行RunId integration-01。当前资格、全部失败及所有实际命令/报告必须入包；精确UUID命名的历史累计save(state)副本可索引恢复；全量文件名/内容哈希闭包扫描保留standard-907aa290真实引用，其余237份仍在Git且已逐字节核验。当前命令、报告、失败、反例、资格和最终四场景文件均随包，15MiB不放宽。

最终构包增量按影响验收通过，当前统一结果`f3ddedfe750f4199b0615ebf19426651`：engineering/package/policy实际成功；原PG五层再次只读重开全部PASS。完整SelfTest 486项发生在4e20，之后仅构包消费者/证据登记由当前受影响门禁覆盖，不把旧full输入冒称完全相同。

3fb候选精确测量16,077,589bytes超15MiB，未生成ZIP。非作者核实八份固定path+SHA旧PASS资格包装已不被当前消费者引用，其45项实际命令/报告继续随包，旧包装原字节保留Git；新增守卫拒绝内容变化或重新成为当前引用，不能泛化为PASS通配。毛节省614,240bytes（0.5858MiB），最后实际大小继续严格测量。

八份精确旧PASS元数据策略的最终受影响门禁`8032e41c6b604efe9ca6e0b7ebb13b78`已通过：engineering/package/policy均真实exit0、零skip；其原件随包。其余交付后验只写包外JSON，保持最终ZIP不可变。

## 2026-11-17 入口修正

授权见 entry-fix-01/authorization.md。Master单写，entry_fix_review非作者只读。Base=b5e3b65d1a3359e8fd778700f525321333df61d2，原分支及Worktree。owned_paths严格限附件第3节；产品源码/合同/依赖/历史证据只读。AC-01所有资源创建入口共享冷准入，AC-02同一真实长场景入口即时核前提，AC-03首代表性证据自动纯测量。AC-01/AC-02定向入口验收通过；AC-03实际plan自动精测19836930字节并在15MiB硬限前拒绝，无新正式V3。非作者源码审查PASS_ENGINEERING_SCOPE，源码候选4414963eaff256f3437c167dc493206998661ea9。复用既有测试及账本，证据批次entry-fix-01，运行资源Run仍integration-01。原已审V3＋完整工程patch/实际原件/回执/非作者审查交付，停ChatGPT复审。

阶段B收尾：资源入口17、工作流21、M4兼容16、公共预检12、构包兼容133项定向测试通过；当前构建绑定与同一原查询会话短拒绝已实测。完整MAF/ABA本轮NOT_RUN，原产品只按已审基线复用，首次超时及旧realm404原因UNKNOWN。工程完整差异/原始双流/机器回执/审查原件由普通工程增量资料ZIP承载，非正式V3；Git及最终资料包后验见包外回执。main只到b5e3，阶段B停ChatGPT复审。

## 2026-11-17 EF-01 去重兼容续作

授权：[entry-fix-02/authorization.md](../evidence/G4-M5-INTEGRATION-001/entry-fix-02/authorization.md)。Base=f620b8917b6bf4e25f6484fd67be5216023ee1dd；主写仅workflow.py量包消费/缓存、create-review-package.ps1早期逻辑映射摘要、Workflow.Tests.py、ReviewPackage.Tests.ps1及本卡/授权/新增证据。非作者entry_fix_review只读。资源/场景入口与产品只读；不新增依赖、无服务操作。

EF-01验收：真实生产PowerShell去重输出先复现旧消费者EARLY_REPRESENTATIVE_NOT_INCLUDED；使用snapshot.Mapping和实际成员摘要接受合法共享载荷，当前Head源blob/SHA/长度及Task/Base/Head逐一核对。缺映射/载荷、冲突、错误身份和篡改继续拒绝；缓存协议精准失效并重新解释原始stdout。真实夹具与定向原件归档entry-fix-02，完整工程patch以已审b5e3为Base，另列f620以来窄增量。

EF-01当前定向验证通过：真实旧生产者exit0/旧消费者精确误拒绝RED保留；24项工作流测试、三种真实产消正例、19组真实输出变异及缓存反例通过。公共构包134个唯一用例本轮覆盖完整：整集122项完成后240秒TIMEOUT，保留真实exit-9，仅补11项并复用已过新增1项，不冒称整集进程exit0。非作者协议及兼容审查原文转录见entry-fix-02/reports。最终patch/新增原件/普通ZIP及Git回读由本轮包外回执闭合；原产品及f620工程ZIP不可变。

EF-01源码资格绑定提交4a6486e67c9125c690f92ed3a4bf2d664254695c：四项源码SHA与实际测试输入一致；之后只补本任务证据/状态。仓库静态及schema2证据预检通过。正常push原分支后交ChatGPT复审，main只保持b5e3；本轮未操作服务、未跑numeric/MAF/ABA。
