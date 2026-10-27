# M1 实际资源收尾

状态：ACTUAL_APPLY_AND_NATIVE_ARCHIVE_COMPLETE。先独立具体清单PASS、51同Head双job成功和main59同Head双job成功，再执行；不是DryRun当完成。仅本任务合成资源，阶段人类复审仍待最终ZIP。

|对象|实际before→动作→exit/完成→after|
|---|---|
|40个准确g3-m1命名卷|64总卷（24保护+40目标）→已审计划cleanup-resources.ps1 -Apply→CLI exit0/completed40→24总卷且40目标均absent；80行逐对象40before/40after，exact docker volume rm/exit0，无失败或新增目标|
|SEM/WEB/FIX三托管树|10注册树→逐个archive_worktree，API先queued→list_artifacts确认为3个archived_worktree、FS及Git均无三路径→7树（原6+Master）|
|历史及task refs|38→38，原历史tips不变，三个worker分支/远端refs均保留，Master/main仅按正常提交前进|
|开发工具与保护集|旧6树/24G2卷全保留；doctor -CheckDocker exit0，SDK10.0.402/Node24.22.1/pnpm11.28.8/Docker29.9.2；保留reader实际V2严格1/1、0skip、126文件不变|

原生API没有CLI退出码，receipt中为null；queued不代表完成。最终完成来自归档附件、准确路径不存在、Git注册树对账和refs保留，不伪造API exit0。可恢复入口是restore_worktree的三个准确identityKey，恢复后按锁重建忽略缓存；不自动恢复或重建本轮已删除合成数据。

容量分开记录：Docker CLI Local Volumes名义使用3.916GB→1.84GB，约2.076GB差（CLI已舍入，非物理SSD）；三worker被移除的ignored普通文件逻辑字节2,234,979,143（未硬链接去重）。两者不相加宣称物理释放。Apply日志卷logicalBytes=0是该类型未测容量的占位，不表示空卷或0对象删除。APFS/SSD实际回收NOT_VERIFIED。images16/5.747GB和Build Cache13/500.1MB前后保持，没有image/history/cache全局prune或引擎重启。

保留：Master活动树及其工具/冻结reader/审查产物，原6历史树、24持久G2卷、历史与新任务refs、私有runtime/PFX、共享镜像与构建history/cache。私有测试runtime只作本次绑定/复审保留，所属合成卷已删，不能复用旧runtime文件跳过fresh bootstrap。原始/tmp诊断日志和未打包编译/工具为复审或重建入口保留，不作为额外ZIP交付；旧阶段ZIP不在本次删除范围。

回收后未启动旧G2数据服务，旧持久数据逻辑恢复NOT_RUN；没有把doctor的元数据PASS说成旧PG/Jena/RustFS重新健康启动。清理前本轮新环境真实ready/故障恢复均已验，清理后保护集/工具及保留二进制已验。恢复需动态fetch并fresh g3-governance -Milestone M1 -StartRuntime，不能擅自进入M2。

只读重验：python3 docs/evidence/G3-M1-001/master/reconcile-closeout.py --root <本任务Master>。实际执行exit0，结果resource-reconciliation.json；其live校验只读Docker/Git元数据，不读取卷或凭证内容。计划/原命令/回执/前后全盘点、CI和独立审查各自归档，不重写历史SHA。
