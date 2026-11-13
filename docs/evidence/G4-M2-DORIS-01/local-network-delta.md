# 本机测试入口网络差异（已获用户批准）

VM前提已全部满足，FE首次启动达到容器内部9030健康；宿主连接失败，尚未完成TLS。准确见证：`probe-20261113-01/service-resources.json`和`connect-diagnostic.json`；运行时HostConfig声明127.0.0.1:19030，但NetworkSettings.Ports的9030/tcp为空。短复现IPv4/IPv6均ECONNREFUSED，客户端1042。两次FE启动均已停止、后验非运行；BE只创建未启动，无OOM。原失败保留，不以文档或Running冒充成功。

上游对照：[Moby讨论53256](https://github.com/moby/moby/discussions/53256)、[问题53960](https://github.com/moby/moby/issues/53960)描述仅internal网络下同类发布端口缺失。它们提供定位线索，不证明所有平台同根因；本机原件才是当前失败依据。

## 具体拟修改

`infra/doris/compose.test.yaml`给FE增加本任务独立`local-entry`普通bridge；FE/BE继续共享原internal网络，BE不加入入口网络。宿主仍只映射127.0.0.1:19030→FE9030，无HTTP/RPC/BE端口发布。仅两个已批准镜像和原4/6GiB限额，不改daemon、全局防火墙/hosts/路由，不安装软件，不增加代理/容器或降级TLS。

新增能力必须明确接受：FE在普通bridge上具有出站路由；这不再是internal-only网络隔离。仅固定本机合成SQL、无生产凭据/数据、无外部catalog，应用目标白名单和直接TLS VerifyFull保留；不主动连接外部数据源。不可把loopback发布描述为出站被防火墙禁止。

原A–F及P0申请冻结了内部网络，因此此次仅申请上述本机测试网络差异。用户已明确批准上述差异。接下来原会话/分支/工作树重建本任务停止容器以应用网络差异，保留私有证书和卷；先确认实际loopback映射，再继续最短TLS/只读/取消探针。不扩大其它运行边界，也不另建工程任务。
