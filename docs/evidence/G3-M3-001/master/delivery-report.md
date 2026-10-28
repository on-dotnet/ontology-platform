# G3-M3-001 交付记录

状态：READY_FOR_REVIEW / PARTIAL。本轮M3及E0本地产品与资源门禁已完成；最终唯一V3路径、Head、大小、SHA256和独立重开结果取冻结提交后真实封包回执，不预填未来值。停止于ChatGPT复审，不进入M4/M5。

## 授权与基线

Base=`c8f1040829b2bfe1e9f7e36223092286975643f0`。2026-10-29人类在侧聊明确批准本地真实验证优先，并同步主任务，覆盖旧强制同HeadCI条款。永久政策、根规则、任务、CI触发、构包脚本与正反测试已提交。Actions默认手动；当前交付Head云CI为NOT_RUN，不把本地结果冒充云端PASS。跨runner缓存功能仍保留两次真实远程证明。

## M3产品与验收

四源RDF仍为唯一语义权威；SKOS多语言标签、Scheme/Concept、broader/narrower/related、来源/标准版本/废弃/引用/检索/差异与Synthetic单位、quantitykind、量纲、版本、来源和属性适配已实现。精确RdfTerm/原始字节/散列、强If-Match CAS、事务回滚和幂等复用现有应用服务；独立审批、不可变Release、正式Jena查询、Run/nativeSSE/Last-Event-ID、固定Release回滚均实测。不下载QUDT正式资产，不做通用换算、收费模型或自动发布。

实际业务源码`34080c91b2655655465c201300dba5ad80886d69`的run `a5c476bcb6d14b15ab3fae045405f838`：业务400检查全PASS（M1=56、M2=91、M3=135包含在400内，不能相加）；兼容冻结reader1真实测试/0skip、G1runtime、观测25、trace浏览器4通过。原外层FULL因旧readiness前缀拒绝M3而FAIL/exit2，原文保留。只改4个受影响验收/测试文件，不改产品/锁/构建输入；25控制平面测试与独立Review通过后，源码`651ff9eaa8df0b0ae07851fc901fcf9761411c87`续跑`resume-aa5a1647d6f54c1580191ce4bfabdf37`：故障8/8、性能27样本四类别通过。两个launcher均finally停止exit0。最终是明确绑定的七关组合验收，不把原失败运行改名PASS，也不重复已过前五关。

原API增量47项和UI增量149项均独立验过；首次audit-ab键错误、旧20项矩阵断言、语法重名和临时fixture错误均留有诊断与修正。当前v1/v2精确01–20、v3精确01–22，UNKNOWN/缺项/重复仍拒绝。Web155测试、lint/typecheck/build通过；SelfTest exit0，后续窄修复25测试通过。此前完整真实模块security126/semantic172/publishing60/query49/MCP33均0fail/0skip；backend树从已实测a655642至交付产品输入不变。C#语义最后BCP47去重边界真实RED3→GREEN4和合法私用尾部对照已独立审查。

## E0与实际效率

最终canonical输入Linux cold run40711221901与不同新runner warm run40713115311同key/image/producer校验通过；warm无下载/hash/extract/build。cold的工程temp路径失败与修正保留，warm完整双job成功；后run40715862497完整成功。Mac最终6项真实cold/export/reopen/load/reuse通过；checksum、OCI、平台、损坏和错误来源负例、跨进程短复现止损均永久回归。浏览器状态合同11项真实Smoke、快速故障FAIL及恢复PASS，完整浏览器前自动运行。缓存真正复用不等于总耗时加速：cold12.645s与warm约12.6s，归档I/O仍有成本。

自动timeline汇总55个实际记录区间：跨度43,776,058ms、区间并集2,638,941ms、累计3,815,385ms、重叠1,176,444ms、可观察关键路径754,423ms、同输入重验2次、COMMAND_FAILED11条。仅覆盖已采集命令；未记录间隔、全部等待、Agent活跃/思考与费用UNKNOWN，不把跨度当工时。原JSONL不变，聚合去重和attempt分配方法见efficiency-summary.json。

两次main实际快进：c8→a655642、a655642→929bfd3；main原六DS_Store保留。首集成晚于计划的最早切片窗口，不能追写成早期集成已完成；后续纠偏以真实产品路径为主。最终文档切片按本地优先政策集成，不再重复全量云CI。

## 资源闭环

实际回收15个阶段资源：2镜像、5build history、8本轮Synthetic卷；另有1独立空fixture卷真实Apply。前7项强不存在及自然后续BuildKit代际无回现已独立复核；本轮8卷准确白名单/期限/指纹/后端/空引用，DryRun8→Apply8 exit0、16条before/after、总卷16→8，独立准确no-such验证。旧G2八卷Name/Driver/CreatedAt保持、KEEP三镜像和最新history1kq保留。物理磁盘回收字节NOT_VERIFIED，未全局prune/restart/升级/改DB。

SEM与efficiency已实际请求原生归档，两项均被平台“Another active task still uses this worktree”守卫拒绝；精确KEEP至所属任务引用释放后再原生归档，不手动绕过。WEB两浏览器cwd引用保持；其它旧/锁树、私有runtime/PFX与跨项目对象保留。SEM10份独有ignored日志已核SHA备份；ignored在V3仅聚合索引，不打包内容。

## 限制与恢复

Windows原生及新LOCAL模式Linux宿主NOT_RUN；既有Linux容器/CI不冒充其他宿主已测。真实付费模型/生产/Monaco暂停项沿历史状态；QUDT正式资产未批准。artifact余额不能确认，人类明确保持BLOCKED_ACCOUNT_BUDGET_UNKNOWN；不上传artifact、不发registry、不增付费容量或权限。原生archive守卫与物理字节未知属于明确保留项。

恢复先fetch最新origin/main，读current-authorization、本地优先政策、任务/合同和资源规范；不要把本报告SHA变成未来固定起点。工具链复用项目隔离锁定版本。若未来明确授权再启M3新Synthetic环境，先`python3 scripts/acceptance/g3-runtime.py prepare --milestone M3`生成新prefix/私有配置，再`g3-acceptance-runtime.py --start-runtime --milestone M3 --smoke-fault-check`；不要把本轮已删数据库配上旧realmFile直接复用。冻结兼容reader身份和专用初始化入口见prewrite-reader证据；不安装新依赖、不改全局PATH/SDK。当前仅复审收尾，不自动启动新环境或下一阶段。

## 唯一V3

validation.json使用LOCAL schema2，testedCommit=651ff9e，按提交重算全部源码/脚本/锁/构建/运行输入身份；只允许证据/任务/开发说明及根规则增量，合同/bootstrap包含在身份内。103构包回归、18早检、8手动CI规则测试通过；历史V1/V2/V3保持原校验，新LOCAL不调用gh。三张稳定代表PNG实际deflated1,913,111bytes，其他截图/历史证据由精确Git对象恢复。最终包独立重开/差异/hash的真实结果见封包后置回执；包与ignored内容不入Git。
