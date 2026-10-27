# M2合成验收资源关闭归属

TaskId=G3-M2-001；CLOSED synthetic：仅本任务合成验收运行已结束，产品仍待人类复审，不自动进入M3。原pipeline前12stage与修复后七runtime关口证据分别保留；实际browser263/M2专项91全部PASS，owned launcher stopped/exit0。真实隔离空卷fixture先行Apply，再Apply八个项目卷；所有删除仍待精确已审计划、同HeadCI和执行器重验，当前尚未删除卷。

创建来源：g3-runtime prepare/full复用可信wave2-runtime，随机合成开发身份/realm，完整生命周期TaskId/RunId/服务label和准确卷清单见owned-runtime-lifecycle.json。样例来自samples/g2及M1/M2合成负例；不是生产或用户唯一数据。源码、核心测试/失败/遥测摘要已Git归档；恢复用fresh M2 prepare→core→bootstrap→full，从锁定fixture再生，不要求重放旧随机认证字节。私有runtime/PFX留在Master ignored，仅metadata，不读/打包内容。

准确SAFE_CANDIDATE九卷如下，Driver=local、CreatedAt/fingerprint/references=[]及固定dockerBackend见docker-preapply.json。八个运行卷在资源清单、runtime prefix和真实acceptance独立交叉证明；一个空fixture在cleanup-fixture-created.json有实际创建命令/labels/exit0。没有未知/生产/跨项目卷。

- `g3-m2-8fb61910c7c7-alloy-data`：CLOSED synthetic，可再生；本任务真实UI/API/PG/Jena/RustFS及遥测合成验收运行已结束。
- `g3-m2-8fb61910c7c7-fuseki-data`：CLOSED synthetic，可再生；本任务真实UI/API/PG/Jena/RustFS及遥测合成验收运行已结束。
- `g3-m2-8fb61910c7c7-grafana-data`：CLOSED synthetic，可再生；本任务真实UI/API/PG/Jena/RustFS及遥测合成验收运行已结束。
- `g3-m2-8fb61910c7c7-loki-data`：CLOSED synthetic，可再生；本任务真实UI/API/PG/Jena/RustFS及遥测合成验收运行已结束。
- `g3-m2-8fb61910c7c7-postgres-data`：CLOSED synthetic，可再生；本任务真实UI/API/PG/Jena/RustFS及遥测合成验收运行已结束。
- `g3-m2-8fb61910c7c7-prometheus-data`：CLOSED synthetic，可再生；本任务真实UI/API/PG/Jena/RustFS及遥测合成验收运行已结束。
- `g3-m2-8fb61910c7c7-rustfs-data`：CLOSED synthetic，可再生；本任务真实UI/API/PG/Jena/RustFS及遥测合成验收运行已结束。
- `g3-m2-8fb61910c7c7-tempo-data`：CLOSED synthetic，可再生；本任务真实UI/API/PG/Jena/RustFS及遥测合成验收运行已结束。
- `g3-m2-cleanup-fixture-4f0eb45b63-postgres-data`：CLOSED synthetic，可再生；独立空卷真实执行器fixture。

八个g2-ef979bd04cc0卷均KEEP_PRIMARY_DEV，禁止删除或读取内容；当前0容器，与开工一致，后置仅metadata/fingerprint保留检查，停止环境的live health NOT_RUN，不冒称旧栈健康。旧g2-master私有runtime恢复入口保留。所有旧worktrees/refs/image/history/cache保持；M2两个worker已独立Review/同HeadCI后原生归档，39raw日志逐hash保全，见worker-archive-result.json。

M2私有runtime/PFX、Master树、raw archives、预构包过程证明KEEP_UNIQUE_RECOVERY至复审结束；准确旧canonical050409...用于历史恢复，新canonical39b0fb...用于当前开发，其他固定依赖镜像保留。所有Build history仅报告本轮增量，不Apply、不全局prune/restart/改DB。APFS/VM物理回收NOT_VERIFIED。
