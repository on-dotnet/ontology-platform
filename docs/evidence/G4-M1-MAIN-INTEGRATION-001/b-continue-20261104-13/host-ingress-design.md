# Run13 宿主入口设施适配

I02 实测 internal-only Docker 网络不建立宿主发布端口；Fuseki/RustFS 容器内健康 HTTP 200，宿主 errno61，实际 publishedPorts 为空。原失败保留。

采用已审历史 host-ingress 的固定 loopback → Docker exec 管道设计，所有新执行字节归入本任务 runtime.py。保持已有三/六/五容器组合、镜像、internal 网络、预算和产品只读。没有网络配置放宽、新镜像或安装。

实现选择由 Master 在既有任务适配授权内作出：宿主 Python 标准库守护进程仅监听登记的 127.0.0.1 端口。通过准确 platform-pg 容器内已存在的 Perl/Socket 执行透明 TCP 转发，exec 用户降低为 999:999。目标只能是同 Run 同 internal 网络中已核验容器 IP 与固定服务端口；每次连接重新校验身份、镜像、网络/IP。PG自身使用127.0.0.1；其他为已登记合成内部地址。

固定映射：platform-pg 15432→5432、Fuseki 15303→3030、RustFS 15900→9000、Keycloak 15180→8080、API 15100→15100、Web 15300→15300（共享API网络命名空间）。模块组只开前三项；G3开六项；M1开PG/Keycloak/API/Web四项。源PG不新增宿主入口。不得接受外部目标、任意命令、旧Run、额外端口或抢占现有端口。

最多32个连接；每连接最长120秒；守护进程最长14400秒。原始协议/认证字节只通过管道，不记录；每向64KiB有界块和流控，保留半关闭及二进制。记录listener PID/启动身份、准确ExecID/实际ExitCode、容器内父/子PID及唯一连接token；异常父进程退出后，远端期限仍生效。清理逐token重新核对/proc身份再终止并证明容器内进程不存在；宿主listener释放、全部Exec退出和KEEP验证都须实测。

测试：固定映射与身份负例、端口占用、未知目标、实际二进制双向流/背压/半关闭/取消、连接预算及期限、父进程异常退出后精确进程/端口回收。先当前设施短诊断，再实际回收；独立Review后新T/新Run完整R2/I01及后续门禁，不复用旧T产品结果。

非internal网络/新增proxy容器会改变出站或容器组合，未选用。仅容器内健康探测不能代替真实宿主程序集验收，未用作闭合。主线与M2继续未授权。

后续短诊断确认Docker CLI单次inspect/exec约3秒；冻结context的Unix API健康读取约3–8毫秒。因此正式转发使用同context准确Unix socket的Engine API1.56，仅inspect、非特权exec创建/stdio附接及ExecInspect，目标与权限仍相同；不创建Docker CLI子进程。实际stdio输出必须解析stdout/stderr帧，控制PID不混入TCP。目标被按计划pause时保持透明TCP等待，不将产品故障替换成适配器立即拒绝。
