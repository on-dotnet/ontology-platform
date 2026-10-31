# 本轮准确资源收尾

已审plan SHA=da87815e593a32c1cf6f92e3806e3883ad447b760d55afcb842e20e0a1a8876f，关闭证明提交205e6512f635e55baf7bcb1e764fb209e531c6d3已push/main集成。新8个g2-1c8100ef259a-{alloy,fuseki,grafana,loki,postgres,prometheus,rustfs,tempo}-data实际精确Apply成功；每项删除前元数据/Engine29.9.2/空引用重验，删除后返回准确Name的no-such-volume及stdout[]，不是只靠rm0/列表缺席。实际16→8卷，旧g2-ef979bd04cc0八卷全部原元数据不变。详见resource-apply.json逐命令exit/before/after和resource-after.json。没有读取卷内容，物理回收字节UNKNOWN。

执行器自身经12项独立验收：11隔离fake Docker正反，另真实创建本任务空fixture g2-rfix-fixture-ac8c3e2c00的8卷并实际Apply强不存在；该8空卷与项目8卷分列，不把mock当实删。Reviewer指出先删后建日志的问题已修并复审PASS，旧FAIL和DryRun保留。未扩大公共cleanup执行器的TaskId，也未冒用旧任务授权。

KEEP：当前独立托管树/任务分支用于复审，已push且由Master集成；解除条件为ChatGPT本轮复审关闭、ZIP/回执转移确认且无活跃task guard。准确私有runtime/PFX目录为本树.tools/security/g2-1c8100ef259a；仅本任务合成身份恢复，凭证/证书不打包，后续复审关闭再评估安全删除。node_modules/构建缓存可由本轮锁输入重建；本树.tools/pnpm/pythonlibs指向既有同项目工具，保护链接目标。原17树和main六DS_Store未改变。当前附属树仍活跃，未作为安全清理候选。

全任务AppHost均finally精确停止；Docker Desktop保留日常开发，未全局prune/restart/升级/改DB。原8卷保留验证为元数据及零误删，未启动旧G2全栈，不声明旧栈health PASS；本轮新真实栈通过并停止。shared canonical镜像复用，无新增镜像构建/BuildKit history需要清理。宿主monitor为本轮新有界观察，精确终止与最终窗口结果以包外交付回执为准，不预填未来结果。
