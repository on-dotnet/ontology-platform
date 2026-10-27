# M2真实资源收尾

实际顺序：独立计划审查→候选c0c3d7b6dc43acee7563844570eb40c3776db34f双job CI40541024145 success→main准确FF/push→fixture DryRun→真实错误Engine负例拒绝（17卷未变）→fixture Apply/准确inspect无卷→项目8卷重新DryRun/Apply→17项后验metadata/absence复核。所有删除只对两已审hash计划；完整before-command-exit-after日志见cleanup/。原生worker归档另经dfce同HeadCI40537316476/独立审查，39raw文件132769B逐件hash保全。

| 对象 | 开工 | 清理前（含空fixture） | 实际结束 |
| --- | ---: | ---: | ---: |
| 容器 | 0 | 0 | 0 |
| 命名卷 | 8 | 17 | 8 |
| image IDs | 10 | 11 | 11 |
| Build history | 0 | 2 | 2 |
| Worktrees | 11（10旧+Master） | 13峰值，卷Apply前已归档2worker回11 | 11 |

实际删除9卷=本任务8个已结束合成运行卷+1个空真实fixture；9条rm exit0及after.absent，逐一准确inspect exit1/no-such-volume再次确认。八个g2-ef979bd04cc0保护卷Name/Driver/CreatedAt/fingerprint均完全相同，所有旧受保护树/旧refs tips保持，branchesDeleted=0。没有G2卷内容读取/删除、历史改写或跨项目动作。

Docker Engine名义Local Volumes1.282GB→619.3MB（四舍五入报告约663MB逻辑差），image5.859GB/cache18项609MB均未变。worker ignored逻辑55269038+533191697B已随准确两checkout移除，raw132769B另保留；APFS clone/共享层/VM sparse不能相加宣称SSD物理释放，physicalReclaimedBytes=NOT_VERIFIED。没有global prune/restart/update/改DB。

KEEP_PRIMARY_DEV：准确8个g2-ef979bd04cc0-{alloy,fuseki,grafana,loki,postgres,prometheus,rustfs,tempo}-data；原g2-master私有恢复入口保留。开工和结束均0容器，未启动旧环境，旧栈实时健康NOT_RUN；仅metadata保留验证PASS。本轮M2独立栈此前真实健康/故障恢复八项已PASS，原开发工具链doctor -CheckDocker实际exit0。旧栈必须按历史可信恢复流程运行，不能把停止状态说成健康PASS。

KEEP_FIXED_IMAGES：resources-after.json列出的全部11准确image IDs。新canonical sha256:39b0fb6616a466a05b2ff8c691bb14a63557c70118d433a4b70fd1068b1bef60对应context1e45f836d9837cbc75d23adb3ad37b0ff79a545ef06102a87aa246feea9cc1e5；旧canonical050409...和legacy401e1f...为旧开发恢复，其他已批准固定依赖用于真实开发。解除：对应恢复入口被已验替代且新授权确认无引用；M2不授权image清理。

KEEP_HISTORY：8q69crf65sf5ffy9tfqlapd3a为第一次COPY失败诊断，lpsg3gngs8x1rvrnb25yjoyn0为当前canonical成功冷构建；两者仅报告、不删除。冷构建10→11 image/1→2history，随后cache hit和全部实际验收保持11/2；未用单Ref inspect/列表缺席伪称持久回收。解除：复审结束且另有精确history范围授权，按冻结后端/强无记录/自然生命周期合同处理。

KEEP_UNIQUE_RECOVERY：Master准确托管树、.tools/security/g3-m2-8fb61910c7c7私有runtime/PFX、artifacts/g3-m2/worker-archives、process-telemetry-c0c3d7b、非最终预检ZIP过程证明；任务三分支保留供复审及跨机器引用核实。各对象解除条件为人类复审完成及所需事实已归档，不把私有资料当普通垃圾。已删除卷的旧M2 runtime不得直接重新启动：必须fresh prepare/bootstrap；源码通过原生restore_worktree恢复准确sem/web identityKey，依赖与缓存按锁定入口再生。

当前唯一正式ZIP、最终Head同CI与独立重开必须读后置交付回执；不在本文件预填未来结果。只有完成M2，M3–M5仍未授权。

额外盘点纠正：精确network-set诊断exit1发现默认bridge ID在开工6b56ba.../Apply前1be179.../结束ea6da3...变化，host/none ID和3个默认network名称/driver/count保持；原因UNKNOWN，不能声明network代际未变。任务没有network mutation/restart/prune命令，M2仅volume范围，9卷准确before/after的context/EngineID/version均匹配；image11 IDs/history2 refs集合一致。记录network-metadata-drift.json，不删除history或改DB绕过。
