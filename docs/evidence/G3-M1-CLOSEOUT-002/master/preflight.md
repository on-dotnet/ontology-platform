# 开工实测

UTC开始2026-10-27（准确命令时间见Docker before observedAt；活跃工时UNKNOWN）。git fetch origin exit0；HEAD/origin/main=47935fb2eda3d708e628a1b23ccd897e2250ff33。原main树6个未跟踪.DS_Store保留，独立Master/worker托管树隔离。

普通沙箱Docker socket permission denied；经授权Mac本地执行可连接，非Engine离线。doctor -Root <Master> -ToolRoot <既有M1工具> -CheckDocker exit0：pwsh7.6.8、SDK10.0.402、Node24.22.1、pnpm11.28.8、Docker29.9.2。Docker Desktop4.96.3，Buildx0.38.1，BuildKit0.34.0，desktop-linux单节点。default builder无/var/run/docker.sock，未改默认context或系统配置。

before仅允许metadata：0容器/24卷/16image IDs/16 RepoTags或digest引用/9history/3network。未读取env/凭证/卷内容。APFS与Docker VM物理回收NOT_VERIFIED。准确版本/代际/挂载/容量见docker-before.json。
