# 整分支统一修复轮

状态 IMPLEMENTED / FINAL_REAL_GATE_PENDING。原 whole-branch-review-initial.md 的FAIL保留，未预填限定复审通过。唯一fix worker=m1_web，独立g3-m1-fix树，源码f149021→Master5d7a1ac；证据92e6435→90af715。共享门禁、CI与维护脚本由Master单写；不改生产并发槽/预算，不新增直接依赖、不进M2。

|发现|已实施与实际局部验证|仍需实际后验|
|---|---|---|
|I1延迟导入覆盖|SourceImportSession的工作区epoch/逐源generation，冻结draftId/revision；functional当前state合并。实际TSX处理器/工作区回调13场景RED→GREEN；完整Web122/lint/typecheck/build及SelfTest0，见FIX目录|Master真实File.arrayBuffer延迟期间新名称/其它源保留、导出原字节及恢复clean|
|I2dirty前提|先填必填reason，独立dirty标记；等待textarea实际内容更新，不以立即清空的file input推断异步完成；改变字节导出再重入原文|增强浏览器实测|
|I3跨轮残留|父统一入口每次新pipeline目录、sourceHead/runId和13步骤状态；子运行继承父目录并创建prefix/runId新目录，7门禁各记录PASS/FAIL/NOT_RUN。子进程失败隔离RED1→GREEN4；原Mac规范路径比较失败也保留|本轮唯一pipeline/child实际sourceHead/状态/退出码|
|I4只读背压|仅固定semantic/queries POST且429准确code=semantic_busy，最多5次，等待250/500/1000/2000ms，逐次状态/请求耗时/配置与实测等待记录；写命令/未知码/坏JSON/503不重试，耗尽仍失败。真实回环HTTP RED2→GREEN6|本轮真实服务完整链；原失败只记录429，未捕获正文，不冒称该轮实际返回code已经动态核验|
|M1后端注释|G3BoundaryTests严格只加3行空白/中文循环用途说明，Worker指定文件format通过|统一原生门禁|

资源执行器原先硬编码仅PRE-G3任务，不能伪用旧身份重放。为本次已授权收尾增量准入G3-M1-001，严格只接受同任务已提交归属证明的g3-m1-命名卷；M2/Git/history/image/旧卷均不开放。新增临时Git/mockDocker正负2项先RED，再正确拒绝但测试读错stdout的4个subcase失败，修正为固定stderr后2项GREEN；原40项在该轮全通过，完整42项由本轮SelfTest再次执行。实际Apply须等独立限定审查、同HeadCI/main集成及新白名单，不在此报告预写完成。

所有诊断txt只统一LF/去尾空格，原/tmp日志保留；真实源/manifest不规范化。父/子新目录解决的是未来轮次，旧runtime根的混合状态作为历史事实保留且不作本轮证明。本轮最终以唯一pipeline.json及其唯一child acceptance.json、完整命令exit0与同HeadCI为准。
