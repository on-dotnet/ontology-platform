# M0 专项 B · Mac 开发容器验证

状态：PARTIAL。日期：2026-10-25（Asia/Shanghai）。当前分支 `codex/M0-containers`，调查基线 `e3f0b9694412f7a91b6075be9d7e8d4fac4b890b`，阶段 BaseSha `25eab6f5bfd944dc44c8c77b1a3cbd22ec9468e1`。本记录不改写 G1 历史证据。

## 授权与只读事实

已读取根 AGENTS、PLANS、当前授权、M0 任务卡、冻结合同、backend/AGENTS、AppHost 与 local-infrastructure。owned_paths 仅 infra/development/**、docs/development/local-infrastructure.md、本证据目录；AppHost/锁/CI/公共配置归 Master。初始工作树干净。

`git fetch origin` 在沙箱内被 FETCH_HEAD 写权限拒绝；相同命令 require_escalated 后退出码 0。核对 origin/main 为上述 BaseSha。

`docker version --format '{{json .}}'` 观察 Client 29.9.2、darwin/arm64、context desktop-linux；沙箱内 daemon socket permission denied，因此该项不是成功。升级权限后的 `docker info --format 'OSType={{.OSType}} Architecture={{.Architecture}} ServerVersion={{.ServerVersion}}'` 退出码 0，输出 `OSType=linux Architecture=aarch64 ServerVersion=29.9.2`。

未读取 Docker auth 文件或用户秘密存储文件；查询通过现有 Docker CLI。

## 固定摘要原生平台（OBSERVED / PASS）

AppHost 固定三个资源摘要，Fuseki Dockerfile 固定 Temurin 基础镜像摘要。逐项实际执行 `docker buildx imagetools inspect <以下完整引用>`。首次沙箱查询均 DNS no such host（每项失败），升级网络权限后四项均成功，输出的 index Digest 与引用摘要相同，MediaType 均为 `application/vnd.oci.image.index.v1+json`。

| 镜像引用 | 原生平台 | 对应子 manifest 摘要 |
|---|---|---|
| postgres:18.6-trixie@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6 | linux/arm64/v8 | sha256:a8be76d23699a6c366437e9f80ead007975f24c35e01c9ee0533c6930ab57ac1 |
| rustfs/rustfs:1.0.3@sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b | linux/arm64 | sha256:a3951370f879374cb89cca3b495e05badab38807cc4cd609c54a35f93f6ccd64 |
| quay.io/keycloak/keycloak:26.8.1@sha256:a78d6b79572168cb25886b80a8b5b8d4ed4390743e3eecb810538683e209dd6b | linux/arm64 | sha256:f259c5f8fcfd6e7a55d9a2dc020c63ac8fc788e63bf9d9cbab9f1244d119e5f9 |
| eclipse-temurin:21.0.12.1_1-jre-jammy@sha256:affcab5356e1270ac35d2361ee83135af2f03e8d580eca78a6d5d6fdbf048db0 | linux/arm64/v8 | sha256:900b7ac325b25c3a7b67351d6595403eba379e7d35babed3cebbb0a9fdc54112 |

未替换图像或使用 amd64 模拟。Manifest 的原生平台存在只证明可选平台，不能代替实际容器平台、Fuseki 构建和运行验收。

## 实际运行与归档来源

以下由platform_worker B实际运行并回报，Master暂停B后续写入后在本独立B树串行归档，未伪称B自行提交。后续两条收尾工具调用等待审批随会话中断，无输出/退出码，不计作PASS；Master另执行脱敏收尾查询，见cleanup-observed.json。没有同时写入。

两个无秘密常量的临时进程harness（/tmp/m0-b-run.py、/tmp/m0-b-trace.py）仅用secrets.token_hex生成秘密并注入子进程环境，启动敏感行隐藏；没有保存/打印秘密，也没有读取Docker auth或用户秘密文件。harness不是日常开发入口，不归档随机值。唯一编排始终为AppHost。

两会话均在Master树cwd实际执行：

```text
dotnet run --no-build --no-restore --project /Users/chasen/.codex/worktrees/m0-master/ontology-platform/backend/src/AppHost/OntologyPlatform.AppHost.csproj
```

第一会话VolumePrefix=m0-mac-b-20261025，结束后第二会话使用m0-mac-b-trace-20261025，没有并发冲突实例。B未编辑Master树tracked文件。日志实际包含Aspire AppHost13.6.3+38294b1b31552dae42a516cffa0cbc737ec08976、Starting DCP ... start-apiserver、Now listening on http://localhost:15888、Distributed application started。两次交互stop均返回AppHost exit=0（会话63272/25453均已结束）。保留未信任开发证书、DataProtection默认本机profile key repository未加密警告；未读取或打包该文件。no-build不会重输出ASPIRE010，该警告由Master真实构建证据保留。

## 实际平台、网络、回环与健康

下面docker inspect/docker image inspect查询均exit0；四容器linux/arm64，不使用amd64模拟，共享网络aspire-session-network-neapewvz-OntologyPlatform，restart policy均unless-stopped。

| 容器 | 实际后端绑定 | 命名卷挂载 |
|---|---|---|
| postgres-dpsuefdm | 127.0.0.1:56966→5432 | m0-mac-b-20261025-postgres-data→/var/lib/postgresql |
| fuseki-dbucruvp | 127.0.0.1:57016→3030 | m0-mac-b-20261025-fuseki-data→/fuseki/databases |
| rustfs-qbvfvptr | 127.0.0.1:56945→9000、56946→9001 | m0-mac-b-20261025-rustfs-data→/data |
| keycloak-ytkejubw | 127.0.0.1:57077→8080、57078→9000 | 外置PG keycloak库，无独立卷 |

Fuseki实际构建镜像sha256:648cf618fef451847f3e8117c4dfa9c71ede24bbb89103fd7299601f98937ce3；其他三镜像对应固定index。查询仅选择Architecture/Os/NetworkSettings/Ports/Mounts/restart等必要字段，不输出Env凭证。

宿主限时HTTP探针全部200：15888/、15080/health、15080/alive、13030/$/ping、19000/health/ready、19090/health/ready。Dashboard页面200是跟随重定向的可达性，不等于认证成功。lsof -nP -iTCP -sTCP:LISTEN实际显示15888/15080/15432/13030/19000/19001/18080/19090/14317/18889只绑定127.0.0.1和[::1]，没有通配监听；DCP代理资源端口，AppHost监听18889。部分早期探针session95103/30389未取最终退出码，不把它们计为exit0；以上结论来自后续独立限时成功探针。

## 四资源重启持久化 · PASS

第一harness交互persistence在保留同一进程秘密环境下实际执行：

```text
pwsh -NoProfile -File /Users/chasen/.codex/worktrees/m0-containers/ontology-platform/infra/development/test-resource-persistence.ps1 -VolumePrefix m0-mac-b-20261025 -PostgresContainer postgres-dpsuefdm -FusekiContainer fuseki-dbucruvp -RustfsContainer rustfs-qbvfvptr -KeycloakContainer keycloak-ytkejubw
```

实际exit0，脱敏输出：

```text
Persistence exit=0
Status: PASS
PostgreSql: 重启后随机标记保留，命名卷挂载符合PG18路径
Fuseki: 重启后TDB2测试URN保留
RustFS: 重启后S3签名写入对象内容一致
Keycloak: 管理就绪恢复，外置库引导身份ID与重启前一致
Marker: bf2ba15d9ca6488984024ca5283e2000
Cleanup: 仅保留本次开发探针，不删除卷；不代表生产恢复或业务认证验收
```

第二harness未调用persistence分支（临时代码复制的前缀仍是第一会话，不能把该分支当第二会话复现命令）。本轮只有第一会话执行持久化；随机开发卷不作为可复用日常秘密配置或生产备份。

## Dashboard认证负例与真实Trace查询 · PASS

第一会话无API key：GET /api/telemetry/traces?limit=3、/api/telemetry/resources均401；/traces页面200 HTML不代表已认证。第二会话通过仅进程环境AppHost__DashboardApiKey设置随机key，认证保持启用，key只放X-API-Key header，不放URL/日志/文件。配置依据[官方AppHost配置](https://learn.microsoft.com/en-us/dotnet/aspire/app-host/configuration)、[Dashboard HTTP API](https://github.com/microsoft/aspire/blob/main/docs/specs/dashboard-http-api.md)。

```text
GET http://localhost:15080/m0-trace-probe
traceparent: 00-f839abe3f6f2ae5cde90e09c3e16d304-51e16b517f97f412-01
HTTP 404
GET http://localhost:15888/api/telemetry/traces?limit=10
X-API-Key: [进程随机值，不归档]
HTTP 200
GET http://localhost:15888/api/telemetry/traces/f839abe3f6f2ae5cde90e09c3e16d304
X-API-Key: [同一进程随机值，不归档]
HTTP 200
```

两次实际查询returnedCount=1/totalCount=1；Microsoft.AspNetCore scope中TraceId、parent与输入一致，span619372097a074d1d，service.name=infrastructure-api、service.instance.id=vdbpjsty、OTel1.20.1。脱敏真实响应节选见trace-query.json，证明真实OTLP ingest与认证查询，不外推完整LGTM。

## 收尾与未运行项

Master实际收尾查询见cleanup-observed.json：docker ps -a exit0/无容器；六个上述两会话专用卷均存在；lsof仅查十个固定端口exit1且无输出，表示该查询未找到监听，非工具异常。本轮没有删卷或清理其他项目数据，停止后不留下运行开发服务。B工具中断的收尾查询没有结果，不与Master实际查询混写来源。

B原树verify -SelfTest两次实际exit1：structured-syntax FAIL/项目parser不可用；外部PYTHONPATH被verify覆盖，本树没有Master新增requirements/锁。创建parser链接的调用随审批等待中断，无成功输出，不宣称恢复。最终完整组合验收由Master集成后真实执行并另存证据；B旧树失败保留前提说明，未降低解析器/哈希要求。

B没有执行Linux CI、标准总ZIP或独立审查；Windows M0运行NOT_RUN、Linux容器运行NOT_RUN；生产/SEC/FE/OBS/G2未开展。状态PARTIAL等待独立Review与Master集成，不以本文Owner自报当独立批准。

Master接管后的额外OBSERVED：.tools/pythonlibs实际已是指向Master已校验目录的符号链接（ls/readlink exit0）；此前中断调用可能已部分创建链接，不能把未取得完整输出推断为没有任何效果。Master在最终归档前实际运行 pwsh -NoProfile -File scripts/verify.ps1（不带SelfTest），exit0、131文件静态检查通过。没有把该次静态PASS替代此前B完整SelfTest失败或Master真实产品组合验收。

独立Reviewer证据边界：以上运行记录为B实测后Master转录，并非原始工具输出；Reviewer只独立重查停止状态、卷、静态规则和源码一致性，未独立重跑历史运行。Master将另以新专用卷直接归档原始运行输出以补齐总门禁。秘密仅进程注入不能保证操作系统或Docker/服务内部绝对不落盘；本报告只保证没有主动将秘密值写源码、日志、证据或独立秘密文件。
