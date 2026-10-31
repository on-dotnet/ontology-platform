# 跨平台 Compose 部署设计 · PREP v1.1

本设计不是可执行 Compose 文件。compose-plan.json 是离线合同输入，全部 image=null、runnable=false；本轮没有 build/pull/up/config。真实入口必须在下一授权完成 image digest、平台、许可及健康命令验证后才生成。静态检查通过不能表示一次启动可用。

## 配置与服务边界

建议下一阶段在独立实验目录生成 compose.yaml（共同配置）、compose.dev.yaml（源码热更新）、compose.poc.yaml（合成数据和严格资源上限）；共享一份服务和端点事实，override 只改差异。core 对应普通入口无 profile；当前概念 JSON 的 core 是角色标记，不能原样转成 Compose 的 profiles:[core]。parser/ocr/ollama/eval 显式 profile，禁止默认开启。知识 Worker 先作为现有 API/任务宿主中的角色，不强制新增微服务。

| 服务 | 依赖/健康检查设计（待映像实测） | 持久化和网络 |
| --- | --- | --- |
| web Next.js | API可用；GET内部健康路由，启动超时有界 | 无持久卷；仅API受控入口代理浏览器路径 |
| api .NET10 | 独立live/ready，PG/Jena/RustFS/Keycloak依赖故障使ready失败 | 内部网络；唯一loopback8080入口；Model Gateway模块是唯一Secret消费者 |
| postgres | pg_isready加独立schema/连接验收；不将TCP开放当ready | 独立任务named volume；无宿主端口 |
| jena | canonical既有内容寻址镜像；只读健康ASK针对独立实验dataset | 新任务独立数据；绝不挂载G2/G3 volume、不写正式图 |
| rustfs | 采用对应精确版本官方health/readiness路由并真实对象往返 | 独立合成对象volume；不能凭S3端口通宣告健康 |
| keycloak | 具体版本management /health/ready及realm登录验证 | 独立实验realm/DB；不改现有登录协议 |
| otel | health_check extension的本地健康端点 | 最小OTel，不默认完整LGTM；不记录原文/凭据 |
| parser / ocr | 进程ready+本地合成样本完整IR校验；禁运行时下载 | 输入只读、输出隔离；profile显式；模型cache必须预批准hash |
| ollama | /api/version与已允许本地模型digest核验分别记录 | 可选独立模型cache；本地模型禁止cloud fallback |
| eval | 有界一次性任务退出码+结果schema，非长驻health | 仅合成输入和报告；无真实secret |

所有网络默认internal；本轮模型预算0，无出口网关。未来外联由另行审核的受控proxy放行精确Provider/region/port，DNS解析/IP范围复核、TLS、禁止redirect和代理绕过；增加外联网必须改合同并负例验证。除API loopback外不暴露PG/Jena/OCR等。Browser登录/回调、反向代理与host端口必须在下一阶段整栈验收，不能把本轮静态拓扑称为完整产品。

## 镜像、权限与开发override

镜像登记格式为registry/repository@sha256:<平台manifest digest>，另记manifest-list digest、architecture、OS、构建全输入key、license/SBOM和本地image ID。未知digest阻断，禁止latest或自动用另一架构。Jena必须复用仓库canonical构建输入和已校验共享镜像，不新增随机build。不同平台不能共用未经验证的本地cache key。每个输入/版本/平台故障先最小复现，禁止同失败整栈盲跑。

设计要求read_only、非root、cap_drop ALL、no-new-privileges、tmpfs有大小上限、CPU/RAM/PID限制、start_period/timeout/retries有限。概念JSON统一10001只是目标，不代表厂商映像兼容；PG/Keycloak等实际UID、所需写目录和初始化流程要逐镜像确认，不能为启动成功改成privileged/root。dev只对白名单源码加只读bind，产物在独立卷，禁止整个HOME、Docker socket、.git/.codex和私有凭据bind。自动重启策略不得掩盖持续失败，实验应on-failure有限次或不重启。

| 主机 | 目标Linux平台 | 必须额外验证 |
| --- | --- | --- |
| macOS ARM64 / Desktop | linux/arm64原生CPU | ARM wheels/镜像；Docker无Apple Metal透传假设，宿主Ollama另授权；QEMU仅诊断 |
| Windows AMD64 / Desktop WSL2 | linux/amd64 | Linux Containers模式；WSL ext4源码；非管理员安装；UID/ACL、大小写、LF、文件监控、host.docker.internal、Secret权限 |
| Linux AMD64 | linux/amd64原生 | glibc/CPU指令、rootless权限、磁盘限额、Docker组策略；GPU仅专项批准 |

[Docker多平台文档](https://docs.docker.com/build/building/multi-platform/)说明构建平台与运行平台是独立维度；本轮三个平台运行均NOT_RUN。主机stdlib实验是macOS，不代表linux/arm64容器已通过。

## Secret、生命周期及下一次真实验收

Secret只给api的/run/secrets/<name>只读挂载，文件不在Git/镜像层/environment/build ARG中。Compose file secret是宿主文件bind机制，并不加密宿主文件；宿主ACL和加密仍需单独管理。[官方Secrets说明](https://docs.docker.com/compose/how-tos/use-secrets/)

创建时登记TaskId/RunId/Owner/ComposeProjectName/精确ID/labels/Purpose/CreatedAt/LastUsedAt/SharedRefs/RetentionPolicy/ExpectedDispose/ActualResult/后端代际/容量。项目名ontology-g6p0-parser-001只是未来约定，本轮无真实创建。停止服务和删除数据分开授权；清理默认DryRun，需准确计划hash、期望ID/版本、24小时期限、同任务关闭且可恢复证明，执行前再验全部KEEP及跨树引用。API不存在/后端断连/列表缺席不能代替删除成功，日志必须before-command-exit-after，禁止prune及批量down -v误删。build history按永久规范需要准确ID持久无记录及自然生命周期复验。

未来Go条件：精确批准镜像与Secret就绪后一次up -d --wait，健康→真实登录→合成文件入库→异步任务→候选审核→版本可用→Agent检索；失败注入网络/存储/身份/取消/重启，退出后精确回收自身资源并保留一套有主人的开发环境。该流程属于后续授权，不在本轮执行。
