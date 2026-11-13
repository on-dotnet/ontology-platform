# Oracle 本机开发切片

本任务仅运行冻结的Oracle 26ai Free ARM64 23.26.3.0.0；精确镜像和驱动见[准入与执行记录](../evidence/G4-M2-ORACLE-01/admission-request.md)。生产及正式验收一体机由用户另行管理，本配置不连接该设备。G4组合根仍仅允许Development，生产参考显式关闭G4和自动迁移。

源库只在internal网络监听，任务API同时连接源网与平台网；PG/OIDC不连接源网。Web/API/OIDC宿主端口为回环15300/15100/15180。Oracle4GiB/2CPU、PG512MiB/0.5CPU、OIDC1GiB/1CPU、API512MiB/0.5CPU，总容器上限6GiB/4CPU；512MiB测试容器与API交替运行。镜像展开≤13GiB，总磁盘峰值≤40GiB。固定relay只用于开发容器回环访问OIDC及宿主Web，单端口最多32活动连接，每连接60秒，不记录正文。

当前工作树保留任务runtime和准确资源记录。使用`workflow_m2_oracle.py preflight --task G4-M2-ORACLE-01`检查工程消费者；`lifecycle --task G4-M2-ORACLE-01 --runtime <本任务私有runtime> --prepared <本任务prepare回执> --output <全新本任务回执路径>`只消费已就绪服务，不创建、安装或下载。构建绑定不匹配即停止。它报告实际UI检查，不能替代完整验收/资源收尾。首次建库的fixture.sql含口令占位符，不能直接粘贴运行；控制器必须核准准确TaskId/RunId、全新合成PDB和seed PUBLIC基线后，内存注入随机口令。

产品只持凭据保险箱中的ORACLE_READONLY引用，固定oracle-source:2484/FREEPDB1/FIXTURE_READER和PRODUCTION、CaseOwner。源管理员不挂入API。客户端仅CA/wallet公开信任材料；服务私钥留源卷，应用KEK/PFX/KeyRing留本任务私有目录。新引用只能绑定同一actor/scope/purpose，轮换增加版本并使旧探测失效；信任材料变化也使旧Probe/Enable/进行中结果失效，必须重新测试。

reader启用原生READ ONLY并仅授CREATE SESSION及目标直接READ；每连接再设session READ_ONLY。G4_CONTROL无登录，仅固定证明视图拥有者读取管理字典，不向reader授广域字典权。元数据仅ALL_*受控两owner，100对象/2000列/2MiB；LOB只描述类型，不读取业务值。NUMBER未知精度、负scale、DATE、时间类型、字符单位保持原语义。取消通过真实驱动token关闭连接，实测范围及限制见准入记录。

备份须在同一任务停写/停服务后，按准确资源记录备份Oracle数据卷、平台卷及各自私有wallet/KEK/KeyRing；私有材料分开受控保存，不进Git/ZIP。恢复必须使用新的隔离卷和同一精确版本，先验证证书、账号原生只读及PUBLIC基线，再验证目录和凭据解密；原卷保持KEEP直到恢复校验完成。本轮已对平台PG逻辑备份完成隔离真实恢复（11表行数/内容摘要一致），并从Keycloak正常关闭后的私有备份启动隔离副本、核对准确realm的OIDC响应。平台Compose使用tmpfs，不能只保留卷名：必须先验证持久备份再停止最后挂载。Oracle数据卷仍KEEP；完整Oracle卷灾备恢复未演练，不将平台恢复或元数据读取称为整体灾备成功。

版本升级先另冻官方精确digest/包锁和容量，再复制隔离数据验证；回滚复用旧版本及升级前匹配备份，不能让旧二进制直接打开已升级卷。当前不自动升级或接受许可。源日志轮转20MiB，命令证据和私有运行日志分别保存。收尾只处理准确任务ID/标签匹配且无活跃引用的资源，保护用户镜像、唯一数据和私有密钥；禁止全局prune/restart。
