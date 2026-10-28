# M3真实门禁入口：受控失败合同

新增owned路径为scripts/acceptance/g3-m3-browser.mjs；Master另行明确分配，未修改其它验收脚本。node --check真实exit0。模块缺失时测试RED，实施后受控503触发FAIL、完整保留部分checks和NOT_RUN，测试exit0；guard-green.txt只证明失败记录合同，不是产品验收。

m3-api.json由注入的**受控503替身**生成，没有访问真实HTTP/OIDC/PG/Jena。其scope字段说明入口预期范围；status=FAIL与profile阶段失败是该负例预期。实际M3完整服务/API/UI/发布/查询/Run/SSE/回滚均NOT_RUN，必须由Master集成到真实环境后执行，不以这个fixture或语法检查提升PASS。sourceHead是测试时已提交4b83736，入口本身尚在工作补丁中；不宣称最终同Head产品证据。

入口：runM3Checks({root,origin,operator,audit,single,viewer,check,command,apiOnly,uiOnly,setPhase})。origin限定HTTP回环，证据限定当前G3-M3-001任务目录；所有认证上下文由受控外层注入，不读取认证文件，不输出headers/会话/服务正文。

真实API计划：新建g2四源+samples/g3-m3/units.ttl+独立SKOS多语言/notation/definition/标准；完整scope拒绝；If-Match缺失/旧revision/任一hash/旧对象冲突；后项冲突保持整批原字节；双源一次revision；原命令重放与冲突payload；真实PG/RIOT读回；真实错误首选标签/单位量纲诊断的source/hash/focus/path；当前profile五阶段完整评估。

真实UI计划：默认source→术语目录/搜索/多语言；排队后切源码保留/只读→取消不写revision；从精确源旧字段替换首选名称；属性nominalUnit由K-v1改为C-v1（明确同量纲IRI，不做换算）；真实revision/全部hash/完整旧RdfTerm请求校验；窄屏panel/selection/overflow；复用fullChain同资产的异人审批、RustFS/Jena正式查询、Run/SSE、第二Release和回滚。要求fullChain明确返回{assetId,release1,release2,runId}，不能读旧文件兜底；Master负责共享函数返回值。

回滚后逐一读取两个固定Release词汇，核对各自manifest hash、revision、全部源hash和profile；验证旧版保留及完整scope403，再从真实UI读取固定Release词汇来源。

apiOnly只执行真实API子集，报告明确NOT_RUN UI/发布/正式查询/Run/SSE/回滚；uiOnly和完整模式都执行API+UI+完整发布链。任何检查失败立即保存FAIL和当前phase，不能吞异常标PASS。独立Review和真实执行由Master完成。
