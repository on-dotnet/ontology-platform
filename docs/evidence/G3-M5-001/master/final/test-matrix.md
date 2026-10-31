# G3-M5 / E0 最终本地验收矩阵

状态：适用本地验收PASS，交付总体PARTIAL。源码冻结`80adf4756f3c6da9a5e1be4a0e348ebdd72e2f69`；[输入绑定](input-binding.json)说明早期稳定套件与后续受影响增量，后续仅任务/证据/研发说明提交。CI NOT_RUN。不同集合有包含和重叠，不能相加为独立用例总数。

|层/实际入口|最终真实结果|证据与范围|
|---|---|---|
|真实RIOT最短切片；PG+RIOT M5|6/0/0；57/0/0|`master/b1-riot`、`master/b1-pg`；保真、历史修订/重入、hash篡改、跨组织/厂区、只读无写副作用和失败关闭。57包含纯投影守卫，不能称57个均调用外部服务|
|完整Semantic + 新增真实负例|296+6=302不同用例，全部PASS、0skip|`master/semantic-full`、`master/riot-negative`；新增6已定向真实RIOT验证，不重复已通过296。restriction malformed/literal/constructor及513节点预算拒绝均有真实解析负例|
|完整Publishing / Query / Agent|78 /49 /33 PASS，均0fail/0skip|`master/publishing-full`、`query-full`、`agent-full`；普通资产正式发布/查询/Run等历史行为保留|
|Web完整单测与工程|268 PASS；lint/typecheck/build exit0|`command-outputs/web-full.txt`、`web-tests-final.txt`、`typecheck-final.txt`、`web-build.txt`。初次生成快照漂移失败已由真实Kestrel导出修复；失败历史保留|
|真实组合根/OpenAPI/HTTP|DI正反2；Kestrel2；HTTP10个不同用例PASS|HTTP先9PASS+1条件skip，再真实OIDC runtime下精确补1/0skip；不把原skip覆盖成一次10通过。见对应command-outputs|
|契约与构建/格式|Ajv3正6负；Release0error；dotnet format0|真实发布合同保持；仅既有ASPIRE010 warning。新接口生成物来源于真实运行OpenAPI，无手补schema|
|M5真实API/UI纵切|API35；首UI47；发布ID修复UI49；最终UI50 PASS|最终run`202fd26ff8bb4362914bb81a98623fdc`，包括固定Release读取、跨厂403、无效revision422/不存在404、源字节导出、深浅/键盘/390、依赖故障与恢复。每个run分别保存，非独立项合计|
|M1–M4完整真实浏览器+M5组合|638 PASS = 原600 + 最新M5专属38|[browser-composite.json](browser-composite.json)。原完整626项625PASS/1FAIL，原因验收脚本误用顶层releaseId；原exit1/report保留。修正后只复跑M5范围，不盲重跑600；不能声称一次七门禁命令exit0|
|普通资产业务闭环|原600全PASS|普通命名公理/单位/身份时间、真实审批发布、正式SPARQL、Diff/Impact、旧Run/SSE/MCP、回滚均来自原真实浏览器。高阶源虽可保存只读，复杂结构仍阻断编辑/发布，无reasoner/import联网加载|
|旧制品严格reader / G1回归|两个门禁分别exit0|`master/remaining-six/{compatibility-binary,g1-regression}.json`；126成员保留reader先冻结/原命令prewrite0，实际读取V2产物，无重编译reader替身|
|观测 / trace浏览器 / 真故障 / 性能|25 /4 /8检查PASS；29个实际性能观察汇总PASS|`master/bounded-four`，四门禁分别exit0/finally launcherStopped。观测先缺输入、后持久trace search不带时间边界失败；短复现证实recent0/bounded1后按真实span限制时间窗修复。仍用90秒预算。性能为原窗口实际样本汇总，不冒充M5新测SLO/负载认证|
|视觉廉价回归|3 PASS/0skip，非作者独立再验3PASS|真实生产CSS fixture，dark/light稳定布局、enabled按钮对比度>10:1、侧栏inert画面遮挡负例；不替代真实React/OIDC。无产品CSS/Token修改。最新三PNG已视觉重开并通过真实尺寸早检，压缩752799字节|
|工程SelfTest|实际exit0，相关后续增量均受影响短验|`command-outputs/selftest-after-baseline-format.txt`；ReviewPackage103、Cleanup60、timeline17、Host12、Evidence23、日志3；Preflight最终12、runtime25、BrowserDispatch6、Frozen5、ObsInputs5。这些工具/fixture测试不能代替上方产品验收|
|实际资源收尾|8准确卷已删；原生Web树归档；2树guard KEEP|`volume-apply.jsonl`与强不存在`volume-postconditions.json`；旧G2八卷metadata前后一致，无全局prune/restart。看[资源说明](resources.md)|

[二十项能力矩阵](../../WEB/capability-matrix-draft.md)逐项给V/S/R/B/L与五维支持，原15裸integer为INDETERMINATE，其余原文件新投影RO是静态核对/综合真实样例依据，未逐份发20个M5端点请求。profile仍v4/23，历史v1–v4与hash未改，projectionVersion1不等于新增语义支持profile。

E0最早防线覆盖路径/CLI、真正audit注册和DI/阶段消费者、失败身份与短复现阻断重复昂贵失败、EOF/证据Schema/PNG真实尺寸、日志自扫描、真实退出码与计时分离及宿主策略，具体正负测试见[失败防线矩阵](../../E0/failure-prevention-matrix.md)。Master额外入口误用及原失败如实保留，未将工具纪律宣传成零误差。

未运行/边界：Windows与Intel原生、实际CI、付费LLM、生产环境NOT_RUN；Monaco BLOCKED；OWL逻辑一致性/推理及imports闭包加载无授权实现。活动/思考/等待时间UNKNOWN。Mac的防idle sleep只在已确认AC政策及观测窗口成立，不保证停电、主动Sleep、重启、更新；完整闭合取包外精确PID回执。正式V3成功只证明构包/完整性，不将上述未知项升格PASS。
