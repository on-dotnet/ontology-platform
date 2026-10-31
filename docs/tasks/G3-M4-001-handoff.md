# G3-M4-001交接与外部复审入口

范围：仅M4。Base=3992582e03df1a103fac36e7e82b8c81f85f622e；最终完整本地测试提交=9ae30173cf900524c387489f48a97fbb244c9d07。Slice A已先入main d134522；B公共合同冻结后独立Worktree实现、首Diff/首Report真实联调、批量独立Review后合成。当前产品输入已稳定，final-input-binding.json逐路径绑定，后续证据/资源回执提交不机械重跑通过的产品门禁。

实际：Web225/0/0+lint/typecheck/build；Semantic239/0/0；Publishing78独立组合（原77PASS/1FAIL，精确旧并发catch修正后仅该1PASS）；Query49/0/0；Agent33/0/0+schema3正6负，实际child0，外层CLOCK_DRIFT保留；HTTP安全10；最终完整七门禁全0、browser600、Smoke11含预期隐藏canvas快速FAIL/恢复、真实PG/Jena/RustFS/OIDC/异人审批/active查询/旧Run/SSE/回滚、原冻结126-member reader读真实V2、Trace及依赖故障恢复、29条局部性能观察均已通过；最终工程SelfTest实际child0，ReviewPackage103/0。性能仅本地Synthetic，不能推生产SLO。

失败均保留：初始前提/路径猜测/显示日志格式、报告审计action未登记9项整事务回滚、语义两个漏洞及envelope角点、MSB4166（failure目录已无，具体原因UNKNOWN，单节点禁复用廉价编译恢复）、旧并发保护码断言、CLOCK_DRIFT。固定Actions已登记，精确IRI/声明消费角色/时间边界有真实正反回归。效率纠偏已追加现有规范，不新增泛化框架。实测时间/重验/重叠见efficiency-summary.json；Agent思考/活跃及未观测间隔原因UNKNOWN。

资源实际回执：main已快进/push获审f933；本任务八卷和此前空fixture一卷已真实删除，精确API强不存在，旧G2八卷metadata不变。A两分支已用remote expected-tip lease/local expected-old CAS删除并逐ref验证缺席。两B树的原生归档被“Another active task still uses this worktree.”拒绝，B refs仍checkout，准确KEEP/DEFERRED_ACTIVE_TASK；原生工具未返回其它task ID，owner UNKNOWN，须真实解除引用并重新独立审查后再原生归档，不直rm/不动其它chat。58份原始ignored任务日志142500 bytes已精确备份并重算hash。旧15树、Windows602草稿、共享canonical/history与Master私有runtime/PFX/reader/cache均保留准确理由/解除条件。卷16→8、树18→18、A本地/远端各删2；物理回收容量UNKNOWN。具体before/command/exit/after和所有KEEP见mac-master/closeout。

唯一正式V3将在真实收尾回执提交后从最终Head生成并独立重开；最终ignored artifact回执提供ZIP路径/大小/SHA及封包/重开实际计时，避免自引用Head和第二正式包。产品源码与已测输入不变，不重跑已过完整门禁。

风险矩阵：

|项目|状态/边界|
|---|---|
|M4适用本地产品门禁|PASS，按精确输入绑定；Publishing为显式组合通过|
|GitHub Actions|NOT_RUN，本地优先按需政策；不冒充同Head CI|
|Windows/Intel原生|NOT_RUN；源码路径大小写/保留名/分隔符检查PASS，Linux容器不代宿主|
|计时|存在CLOCK_DRIFT，原日志保留；时间有效性分列，不能用命令累计解释长墙钟|
|Monaco|BLOCKED / PAUSED_BY_USER|
|真实付费LLM|NOT_RUN；只用既有deterministic/disabled模式|
|完整OWL/外部imports/G4连接器/G5计算|未实现；未知覆盖与技术阻断显式保留|
|生产HA/SLO/供应链专项|未完成；本地Synthetic观察不代认证|
|受保护资源|2个B树/B refs因原生活跃task guard保持KEEP；实际owner UNKNOWN，解除引用后重新审查|
|资源物理回收字节|未测项UNKNOWN，du为目录估计，不冒充物理空间|

不得自动进入M5/G4/G5。最终ZIP独立重开后输出G3_M4_READY_FOR_REVIEW并停止，等待ChatGPT复审。
