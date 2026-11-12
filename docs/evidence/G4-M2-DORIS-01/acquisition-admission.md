# 条件获取准入核对（非运行放行）

TaskId G4-M2-DORIS-01；RunId admission-20261112-01。用户已确认VM调整，第二次Engine读回16,787,419,136 bytes/aarch64/29.9.2，当前无运行容器；首次7.75GiB记录保留，未启动设施。宿主能源preflight POLICY_READY，锁屏/熄屏连续性仍NOT_VERIFIED，长运行前还需用户能源确认与有界见证。

## 获取集合

FE/BE index→ARM64 manifest→config原始字节hash/size/平台全部匹配批准值；25个层描述符去重为15个，3,660,429,743 bytes（约3.41GiB）。全部25次HEAD长度匹配；config仅转向已批production.cloudfront.docker.com。层HEAD不保证GET域名，获取器逐次重验。metadata/ledger.json记录35,734 bytes；新增NuGet校验元数据单列，累计计入64MiB预算。

本任务artifact-cache为空，尚无可验证compressed blob命中。本地既有Docker镜像不含Doris，底层共享blob不可从image列表证明，故不计任何复用折扣，按15层全量保守预留；不删除或改动其它镜像。获取时只消费清单15个digest，已在本任务缓存且sha/size/完成记录一致者跳过。无法证明共享层命中不写MISS/PASS，状态NOT_VERIFIED。

有效NuGet新增仅MySqlConnector2.6.2（3,842,388 bytes）：Connections/API/四个相关Tests经本地SDK10.0.402的AddPrunePackageReferences实际求值exit0，均net10.0/RestoreEnablePackagePruning=true/ASP.NET框架，两候选裁剪上限10.0.32767。AppHost只有NETCore框架、没有两项裁剪，但其三平台既有锁两项10.0.12已满足≥8.0.2，不新增或降级；Governance既有10.0.13原样保留。Logging8.0.2 net8仅依赖DI8.0.2，DI net8无依赖；仅作为闭包元数据，不下载被裁剪候选。离线实际restore后如出现其它新增载荷或现有版本变化立即停止，不以此次求值替代最终lock审查。

总计划载荷3,664,272,131 bytes；距5GiB上限约1.58GiB余量，NuGet<10MiB。全平台锁只审一致性，不下载其它架构。原件保存在本树ignored artifacts/workflow/G4-M2-DORIS-01/artifact-cache；不会复制到公开证据或ZIP。

## 预算、获取器与后置门槛

磁盘基线df可用297,091,732 KiB（约283GiB）；当前任务元数据和命令原件远低于1GiB。获取器每32MiB检查任务目录实际文件大小≤25GiB及磁盘剩余≥25GiB；载荷每1MiB计账并持久化（未完成/重传不扣减），无自动重试，已有partial必须停下审查。NuGet包缓存/解包后另限100MiB；导入镜像前再把VM镜像存储增量纳入25GiB，不把压缩大小当实际解压大小。过程产物独立≤1GiB，原件载荷按缓存计，不伪装日志。

本轮获取器临时路径 `/private/tmp/g4-doris-acquire.py`，归本Task/Run，最终审查后精确回收；不安装工具。只用标准库HTTPS，GET域名精确白名单registry-1.docker.io/auth.docker.io/api.nuget.org/production.cloudfront.docker.com，最多4跳、跨域删除Authorization/Cookie、token/签名URL不打印不归档；未知域名记录host后拒绝。响应长度严格等于登记size，层SHA256必须匹配；NuGet与官方catalog SHA512核验后方可解包。单对象900s总期限，传输超时30s；未完成保留且不盲试。底层TLS/重传网络流量不可测，NOT_VERIFIED；明确记录应用读取payload bytes。

下载不启动entrypoint、不运行包targets、不导入执行任何程序。下载后安全只读归档成员检查、LICENSE/NOTICE/OS/JDK/组成及漏洞/签名可得性检查，DORIS-LOCAL-01保留未知而不将其标PASS；验签明确失败/内容不符/适用高危/许可禁止停止。执行准入和真实最短TLS/权限/取消探针由Reviewer后续单独确认。

## 逐项目实际求值

- `backend/src/Hosts/OntologyPlatform.Api/OntologyPlatform.Api.csproj`：exit=0；pruning=true；Microsoft.NETCore.App,Microsoft.AspNetCore.App
- `backend/tests/OntologyPlatform.ConnectionsTests/OntologyPlatform.ConnectionsTests.csproj`：exit=0；pruning=true；Microsoft.NETCore.App,Microsoft.AspNetCore.App
- `backend/tests/OntologyPlatform.QueryTests/OntologyPlatform.QueryTests.csproj`：exit=0；pruning=true；Microsoft.NETCore.App,Microsoft.AspNetCore.App
- `backend/tests/OntologyPlatform.SecurityTests/OntologyPlatform.SecurityTests.csproj`：exit=0；pruning=true；Microsoft.NETCore.App,Microsoft.AspNetCore.App
- `backend/tests/OntologyPlatform.AgentTests/OntologyPlatform.AgentTests.csproj`：exit=0；pruning=true；Microsoft.NETCore.App,Microsoft.AspNetCore.App
- `backend/src/AppHost/OntologyPlatform.AppHost.csproj`：exit=0；pruning=true；Microsoft.NETCore.App

获取器审查修正：read1逐次计账并按剩余900秒设置socket期限；token30秒有界读取，累计元数据包含校验元数据及首次gzip失败的1,048,577 bytes保守预留。当前脚本SHA256 `1fb2f01727c8ef053395c7eea74589ccc1aaad72108b0e5fb3c0cd631b94ad88`；用户已确认持续保持能源策略。

非作者获取准入PASS：/root/p0_reviewer核对最终获取器SHA256 `cbde66d6594c81e3f218403e119285b9b2a09e4e9bbd2c8b596c07348b09782b`，仅放行15层与MySqlConnector2.6.2至隔离缓存；未放行运行。read1收尾补充closed/fp为空退出并保留精确后验，标准库HTTPResponse内存回归通过。

公开元数据原字节已通过既有workflow_evidence归档预检并保存base64封装；metadata/originals-index.json列权威原件及SHA，原文件名为仅换行规范化的阅读视图。散列复核须restore对应原件，不散列阅读视图代替原始响应。

## 用户接管镜像下载（2026-11-12）

用户说明网络不稳定，要求提供全部所需镜像，由用户下载完成通知后再继续。Agent停止后续获取及依赖实施；当前没有运行下载进程或产品设施。首个层27,383,877 bytes已SHA256核验，后续HTTP401无载荷；总载荷仍为27,383,877 bytes，NuGet载荷0。匿名token有效300秒，首层耗时740秒；v2按每缺失blob刷新token的窄修复已独立Review，但尚未执行。

用户仅需取得 `apache/doris@sha256:c7b4288a34affac9fe809a2895565b4d558ea3b85fbf5d29bb1ec27d398e4f02`（FE4.0.8/linux-arm64）及 `apache/doris@sha256:1d4ccee8d7cc5e33f1c16e0b3ce764f5f764c396ea5e938a8793f88682c982f7`（BE4.0.8/linux-arm64），context为desktop-linux。其它平台PG/OIDC等基线镜像本机已有，本轮不额外拉取；用户不用启动容器或安装驱动。MySqlConnector2.6.2在镜像通知后由Agent按既有授权另行获取。

恢复时先复验用户实际镜像digest/config/architecture、Docker资源、内容与许可证/风险；手工下载过程网络字节不可观测则标NOT_VERIFIED，不伪造5GiB流量实测。既有27MB私有缓存KEEP用于审计及后续去重，不自动重传或全局清理。最终唯一V3仍未生成。
