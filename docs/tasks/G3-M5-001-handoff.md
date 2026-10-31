# G3-M5-001 复审恢复入口

适用本地M5/E0及G3兼容验收完成，当前READY_FOR_REVIEW / PARTIAL；停等ChatGPT复审，禁止自动G4/G5。Base e5b7e99715ee7ebfe419717f7cacf0c02dfcb78a；最终已审源码testedCommit=80adf4756f3c6da9a5e1be4a0e348ebdd72e2f69，后续仅任务/证据/研发说明。最终交付Head/ZIP/hash及独立重开以包外receipt为准，避免回填SHA循环。main已分批ff/push，原main六个未跟踪DS_Store保留。

合同3e71049先独立审，再SEM/WEB/E0各自托管Worktree并行，公共合同Master单写；至少B1 API/UI和最终全业务两次纵切。restriction及工具退出码/BOM审查发现均已修并短复验。最终[验收矩阵](../evidence/G3-M5-001/master/final/test-matrix.md)、[输入绑定](../evidence/G3-M5-001/master/final/input-binding.json)、[二十项能力](../evidence/G3-M5-001/WEB/capability-matrix-draft.md)、[E0失败防线](../evidence/G3-M5-001/E0/failure-prevention-matrix.md)是恢复入口，不以旧draft当最新状态。

Semantic302=完整296+后续6真实RIOT负例；Publishing78/Query49/Agent33，均0fail/0skip。Web268和工程、实际DI2/Kestrel2、HTTP10=9+1均通过。真实浏览器原600旧业务全PASS但M5验收脚本顶层releaseId错误造成原626中1FAIL；正确嵌套manifest ID修复后只复跑M5，最终真实UI50PASS，组合638PASS。另六门禁分别exit0。缺链输入/Tempo search窗口失败保留并精准修复；不宣称一次七门禁exit0。CI/Windows/Intel/付费LLM/生产NOT_RUN，Monaco BLOCKED，无reasoner/import联网加载/profile v5。

Mac用户自行启用显示器关闭时防自动睡眠，ACsleep0/display10只读验证；锁屏37心跳与官方CoreGraphics同时锁屏外接熄灭13心跳/0Sleep已测。任务级监测PID6932最长12h，snapshot328心跳/82分钟/0Sleep，后续一直监测至正式构包独立重开。精确SIGTERM/全窗口0Sleep及退出码取包外host-closure.json；不能把短caffeinate fixture等同App全寿命。禁止-d/-u、pmset写入、登录项/killall。

[资源实际收尾](../evidence/G3-M5-001/master/final/resources.md)：8自身Synthetic卷真实精确Apply并强不存在；旧G2八卷metadata未变；Web原生归档、E0与SEM两树活跃guard KEEP，不强删。Master当前b389树及私有runtime/PFX/reader保留复审，原生保护与解除条件逐项列出。无新镜像/history构建、共享canonical复用；不全局prune/restart。

恢复只用本轮新生成runtime，不读取/传播历史凭据。Node24.22.1/pnpm11.28.8/SDK10.0.402、Docker29.9.2/linux aarch64；`.tools/pnpm/pythonlibs`为既有同项目工具链接，实际离线store来自g3-m3-master/.tools/pnpm-store。正式容器前先host/path/参数/consumer/evidence预检与compile，用相同输入fingerprint复用已过结果，未变昂贵失败必须先短复现止损。

唯一正式Review V3在Master artifacts/reviews，包含Base..Head全diff、现行源码、当前任务证据各一次；仅3张最终稳定PNG，过程截图由Git精确对象索引恢复。包外独立重开和host终止回执不再回写Git触发重验/重包。模型活跃、思考、人工等待UNKNOWN；[时间分解](../evidence/G3-M5-001/master/final/time-breakdown.json)只报告真实已记录命令和独立宿主窗口。
