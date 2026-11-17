# G4-M5-INTEGRATION-001｜早期量包消费者去重兼容修复
日期：2026-11-17
性质：供用户确认后执行的窄范围续作；本文件不是 main 更新授权。
本次不新建P0、工程优化任务或恢复任务。

## 0. 身份与执行位置

- 继续原会话：`G4-M5-INTEGRATION-001-MASTER`。
- 继续当前 `codex/g4-m5-integration-001` 分支及原 Mac ARM64 Worktree。
- 已集成且保持的 main：`b5e3b65d1a3359e8fd778700f525321333df61d2`。
- 待修工程 Head：`f620b8917b6bf4e25f6484fd67be5216023ee1dd`。
- 原产品V3 SHA256：`8cb48c1f420cb5f3461e2dcff1fc747b5d6e301cdc73248e796179d72b128eea`。
- 当前工程增量ZIP SHA256：`5c3228ebe28d182266edb2d7f78ae5b8cf9534c6592bc6c567226d16356abfc1`。
- 当前工程patch SHA256：`efaf21bd50d6c65eb525efb89c043760c94874c81394dbd89ea9c8b24b3d9a58`。
- 资源Owner/Run仍为 `G4-M5-INTEGRATION-001 / integration-01`；
  新证明可放 `entry-fix-02`，不能替换资源Run或改写 `entry-fix-01` 原件。
- Code/Agent执行；沿用当前编码模型，Medium；非作者在本次协议与反例边界按需High。
- 先给不超过一页的实施清单，随后在范围内连续完成；普通局部修改不再逐项请求批准。

## 1. 唯一待关闭问题 EF-01

严重度P2：工程消费者协议错误；不是新的PG业务缺陷，也不撤销已集成产品结论。

当前代码：
- `scripts/maintenance/workflow.py:400–452` 的 `measure_committed_evidence()`；
- 其中425–428把每个gitPath直接换前缀，要求该同名路径出现在MeasureOnly.members。
- `scripts/create-review-package.ps1:565–575` 的正式V3允许按内容SHA去重，
  `snapshot.Mapping / manifest.sourceMembers`把多个gitPath指向同一实际archivePath。
- MeasureOnly约919行目前只返回物理members列表，不返回足够的逻辑路径映射。

合法输入反例：
两个不同路径的当前代表性JSON（如reports/a.json与reports/b.json）具有完全相同字节。
正式选择只保留一个载荷，同时保留两个逻辑映射。这不是证据遗漏。
但Python消费者会抛 `EARLY_REPRESENTATIVE_NOT_INCLUDED`，工作流plan被误阻断。

ChatGPT已完成：
1. 读取实际生产去重实现及当前消费者；
2. 从本次提交提取原函数，在内存替身中执行：
   - 两物理成员：正常MEASURED_NOT_READY_FOR_ACCEPTANCE；
   - 合法一载荷两逻辑路径：抛上述异常，未产生最终测量回执。
3. 已上传原产品V3中存在424条当前任务相关JSON映射，其物理archivePath不同于直接前缀替换。
这是受控消费者反例，不冒充PowerShell/真实Git小仓或产品运行。
请先核实再修正，不照抄结论；若无法复现，应交精确代码和反例，不以摘要PASS反驳。

## 2. 最小设计

沿用生产Snapshot/MemberPlan/MeasureOnly，不发明第二套入包算法。

- 让早期测量消费者获得生产选择生成的准确逻辑路径到实际载荷的映射。
  优先复用已有snapshot.Mapping及实际Members元数据；仅附加测量输出所需的有界描述。
- 按准确gitPath定位唯一映射，核对当前Head/Task、源blob/长度/SHA和实际载荷的成员身份及内容元数据。
- 多个合法源路径指向同一载荷应被接受；不能要求同名物理文件重复出现。
- 缺映射、映射指向不存在成员、SHA/长度/源blob不符、同路径冲突及错误Task/Head必须拒绝。
- 当前要求随包的代表性证据只有index-only但没有载荷时，不得当成本次已入包。
  既有被批准的历史index-only策略单独保持，不泛化为新证据可省略。
- 不通过删除原检查、忽略报错、按basename搜索或接受任意同SHA文件解决。
- 不改变V3 ZIP布局、去重/历史选择政策、正式LOCAL验收要求、安全扫描或15MiB硬限。
- 不把测量成功写成验收PASS；早期结果仍为MEASURED/NOT_READY_FOR_ACCEPTANCE语义。
- 控制测量响应体积：尽量只返回本次代表路径所需的映射和引用载荷摘要，
  不在每个回执递归嵌入全仓历史索引、全文或完整资格。
- 当前正式构包器内容不应依赖新旧stdout展示格式；保护既有调用者兼容。
- 解析语义变化后不得误用缺必要映射的旧测量缓存；依据真实输入/协议版本精准失效，
  不因此使产品执行资格失效。

## 3. 准许修改的范围

实现：
- `scripts/maintenance/workflow.py`：仅量包结果消费、必要的对应缓存资格。
- `scripts/create-review-package.ps1`：仅早期测量的逻辑映射/载荷摘要输出；
  不改变正式包的选择/结构/扫描/验收要求。

测试：
- `scripts/tests/Workflow.Tests.py`
- `scripts/tests/ReviewPackage.Tests.ps1`

文档与证据：
- 原M5任务卡、必要的当前状态说明；
- 本Task下本轮新增证据/机器回执/准确审查记录。
不新建另一套效率规则，不修改资源和场景入口，更不触及：
backend/src、apps产品实现、Contracts/DTO、数据库迁移、锁文件、五秒预算、生产Guard。
旧产品包、当前工程包、失败/历史原件保持原字节。

## 4. 一条最小验证链，不重跑整套M5

- [ ] 在现有测试夹具中增加两份不同路径、内容相同的代表性JSON。
- [ ] 证明旧Python消费者对生产实际去重输出误拒绝，保留准确RED；
      编译/环境错误不算该反例RED。
- [ ] 修复提供方输出与消费者映射处理。
- [ ] 贯通至少一次真实现有PowerShell生产选择/MeasureOnly输出到Python消费者；
      小型隔离Git fixture即可，不启动Docker/API/PG或浏览器。
      不允许只手工编造members数组就声称生产与消费闭环已验证。
- [ ] 正例覆盖：未去重、两当前逻辑路径共享载荷、代表路径与另一个合法已选路径共享载荷。
- [ ] 负例覆盖：缺映射、无实际载荷、内容/长度/blob不符、冲突映射、错任务或错Head。
- [ ] 现有超限拒绝、非最终测量不生成持久ZIP、正式验收及V1/V2/V3兼容检查按影响保留。
      同一133项集合若受提供方代码修改影响，可运行一次稳定输入的相关构包兼容集；
      不是重新跑全部工程SelfTest，更不是产品全链。
- [ ] 非作者审查必须读生产去重分支、消费者和真实小夹具输出，
      明确证明逻辑证据完整性不等于同名物理文件存在。
- [ ] 源码、测试、原命令、输出、输入身份准确绑定。

不prepare/restore，不新增下载或依赖，不启动/停止/清理任何KEEP。
不重跑numeric、MAF、ABA、自然TTL或M1–M4历史全链。
当前MAF首次超时、旧realm404仍UNKNOWN，格式与平台边界保留。
复用本次已经核验的资源和场景入口证据，勿假称完整业务在新驱动上重新跑过。

## 5. 最终交付与停止点

保持“原已审产品V3＋普通工程增量”交付，不复制14.81MiB产品包。
生成一个新Head对应的当前工程增量ZIP；旧f620工程包作为历史保持不变。
包含：
1. `b5e3...`到新Head的完整patch（新文件全文），并列明`f620...`到新Head的窄修复路径；
2. EF-01正反例与真实生产者→消费者小夹具命令/双流/输出；
3. 包外机器回执：精确Base/Head、FRESH/REUSED/NOT_RUN、失败原件、当前main未含增量；
4. 非作者代码和同工程增量包的路径/散列重开记录。
继续明确不是正式V3，不能宣称正式V3 VerifyOnly已执行。

已有127份命令原件可原样复用；只新增本次必需的证据，不重演旧检查。
按普通提交/push推送原分支，提供实际文件，停在ChatGPT复审。
本授权不允许main更新到当前f620或未来新Head，不进入G5/G6/G7，不恢复TDengine。
