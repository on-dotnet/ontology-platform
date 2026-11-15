# G4-M4-QUERY-001 复审修复与验收矩阵

修复起点 `0ab9658ae7873fe98a927a0202d6f51f391a2371`；最终V3 Base仍为 `f0afb730ce92ecbd3a5947d9c6f58faedc8b2138`。本文件为原任务的实现/证据关联，不新增规格。资源Owner仍为 `query-impl-01`，本轮证据批次为 `review-fix-01`。最终状态及源码/执行身份以本轮validation、原件索引、非作者Review及包外回执为准。

| 要求 | 根因及实际改动 | 可证伪验证与原件入口 |
|---|---|---|
| RF-01 | 原关系执行用完整G4QueryValue的canonical/hash比较，numeric值相等而precision/scale不同被丢边 | 旧实现固定预期2边实际0；[RED索引](numeric-red-index.json)，不是修改断言制造失败 |
| RF-02 | 内部G4QueryKeyEquality先按冻结规则验证，再用精确decimal比较；其他同类型保持词法相等，null不成边，不同/非法类型明确503 | QueryTests覆盖负数/零/尾零、超过double精度的相邻整数、28位边界、复合键/作用域/时间区间及非法值；canonical与DTO未变 |
| RF-03 | 新合成numeric(10,2)/numeric(12,3)表沿正式目录、映射校验、异人审核与激活进入Gateway | 源SQL固定target-1/target-2；真实结果同两条边、证据可解引用、恢复原规范字节；numeric UI与正式MAF恢复分别取原件 |
| RF-04/05 | ABA测试报告增加同mapping/query、UTC和单调事件顺序、实际发布链；原件资格器独立拒绝缺项/倒序/错身份/宽预算/成功残留 | 正式PG读取后真实A→B→A，原5秒预算内409/query_binding_stale，零成功结果/读取回执/审计；负例在WorkflowQuery.Tests |
| RF-06 | 继承独立测试库机制，增强当前容器Task/Run、实际库存在性与服务端Owner/nonce检查 | 无标记既有库、错误容器/Run、运行库名在破坏SQL前拒绝；实际独立PG测试与非空运行query保全/准确回收原件 |
| RF-07 | 完整API输出冻结到新内容目录，只读挂载；验证所有DLL/deps/runtimeconfig/内容、输入闭包、工具和进程；拒绝子挂载覆盖 | 五个真实项目引用构建期间API进程/运行文件不变；准确重启后新授权会话恢复同一旧结果原字节，源扫描不增加 |
| RF-08 | 项目传递引用、合同/内容/配置、测试及驱动与解释/归档分层；未知工程变化拒绝 | 旧861输入原件不改，新投影核原驱动字节/执行AST/原任务用例与构建；新解释器重开原件；断言、fixture、比较器等变化失效，装饰器/动态默认值拒绝 |
| RF-09 | Python预检调用生产Get-ReviewSnapshot成员计划；接近硬限用同构包流程的内存MeasureOnly | 共用成员集合、无中间ZIP、实际15MiB硬限/10MiB说明及安全/V1/V2/V3兼容保持；完整SelfTest中ReviewPackage130例通过 |
| RF-10 | 六态、当前授权、映射绑定、恢复、取消、UI/MCP边界及G2保持 | 本轮受影响产品场景FRESH；未改变Web测试输入的原typecheck/lint及非零单测REUSED，当前解释资格FRESH；不重跑M3历史产品 |
| RF-11 | 历史失败、23 PASS恢复索引、5 FAIL及322旧原件保持原字节；原ZIP不变 | 原ZIP SHA256 `129c77f14b61589be1634cd4fc7f76697ac3cad0c1c1795933b00f75185c7039`；Git基线/原索引保全核验 |
| RF-12 | 当前源码/构建/运行/资格分开绑定；普通提交push本分支，最终同一V3非作者VerifyOnly | 当前validation、原件索引、review与包外回执；CI/其他平台NOT_RUN，外部未取回原件NOT_VERIFIED |

## 本轮失败与根因

- numeric RED前首轮测试夹具缺少必填Label导致编译失败；原编译失败和修正后真正语义RED均保留。
- Docker Desktop把bind source表示为 `/host_mnt/...`，初版快照资格拒绝。仅在Darwin归一该前缀，再精确比对已验证快照路径；子挂载/可写/错路径仍拒绝。
- numeric UI首次页面502，准确Web端口没有监听。复用既有离线构建恢复本任务Web后通过，失败与新环境身份均保存；无下载。
- MAF连续短定位证实旧session仍在有效期但引用的认证key不可用。双API停止卸载原local/tmpfs认证keyring；结果用的持久 `/query-keyring` 不受影响。`s1-reopen`以新正式OIDC会话恢复旧结果成功，而MAF夹具仍指重启前session，故403。保留旧票据拒绝原件，再经正式S1建立新前提，MAF通过；未改权限、purpose或认证合同。该结论不声称旧会话跨完整停机存活。
- 最后定向补验的标准夹具显示名指向S2已终态禁用的旧连接；使用现有replace-disabled-connection入口创建新连接，旧连接保持禁用。新连接只有映射grant，首条S1按默认拒绝；补既有合成查询grant后再测，未放宽产品授权。两次编排前提失败原件均保留。
- 独立Review发现执行AST过滤可能丢掉导入时默认参数/装饰器副作用，及投影wrapper可能覆盖原任务/用例身份。已拒绝未知副作用并严格核原身份/inputsUnchanged，定向反例通过；两项由同一非作者复核关闭。
- 首次原生全文件格式检查351项失败；准确基线行映射后仅修新增问题。最终全文件命令仍exit2，318项均映射至修复起点的同一诊断，新增0，明确为范围外LEGACY_BASELINE；本轮改动格式通过，不冒称全文件PASS。中文XML/局部声明及成员空行另作专项审查。

## 复用、时序和边界

同一解释器更新不改变原执行构建身份；原件投影保留原命令/报告/build/任务/Run/用例/输入稳定性。只改格式的两个测试项目重新离线构建并定向执行；API产品字节未因此重建。源/权限/G2与其构建按原完整闭包核验，Web原测试按确切执行驱动及输入投影复用。没有将旧binary换标为新build。

Mac沿用用户已确认能源策略；本轮有界600秒监测120次心跳均锁屏/显示器关闭，AC和防睡眠策略持续有效，未观测Sleep事件；只证明该窗口。合成设施保持原准确Owner和预算；临时测试容器/随机库准确回收，七个本任务长期组件KEEP等当前复审，不清其他任务资源或历史结果。

D中外部IdP禁用不即时传播的合成环境限制保持。没有更新main、部署生产、恢复TDengine或进入M5。实际执行/构建/构包次数和计时以命令汇总为准；未测时段为UNKNOWN，不以脚本行数或测试数声称提速。
