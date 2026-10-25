# M0 Mac Master 接管与跨平台兼容验收

日期：2026-10-25（Asia/Shanghai）。总状态 **PARTIAL / READY_FOR_REVIEW**：Mac工程最低运行验收PASS；本轮Windows原生重跑、Intel Mac及其他开发宿主组合NOT_RUN，不能宣称所有平台全面PASS。独立源码、组合入口及原始运行证据审查均通过；最终已提交集成头的Linux CI与main状态由ZIP manifest.runtimeCi和Git事实精确绑定。BaseSha固定25eab6f5bfd944dc44c8c77b1a3cbd22ec9468e1；最终已提交HeadSha、main CI和归档校验以标准ZIP manifest及实际构包返回值为准，不编造自引用提交。

## 授权与架构

人类正式批准M0-MAC-PORTABILITY-001及迁移合同第二节至文末，[授权归档](authorization.md)、[任务合同](../../tasks/M0-MAC-PORTABILITY-001.md)、[当前授权](../../tasks/current-authorization.md)。前序G1-INFRA已完成，用户确认其复审通过；原历史报告不重写。仅恢复Mac工程兼容、开发容器及Master协作，SEC/FE/OBS/G2未启动，无生产连接、系统级安装、管理员改动、付费模型API或收费macOS Runner。

保留模块化单体、AI Native、RDF/OWL/SHACL、中文C#注释、Next/shadcn/Base UI/Design System、安全与观测要求；没有C#业务源码或架构调整。AppHost/ServiceDefaults原职责不变。研发explorer/platform_worker/quality_reviewer已实际加载派发，不是产品MAF能力，也不等于OS独立只读沙箱。

## 实际结果

| 项 | 状态与命令/退出码 | 证据 |
|---|---|---|
| 基线/Worktree | fetch成功，origin/main=指定Base，开工干净；三托管树独立分支/管理目录，两个专项并行 | 任务卡、独立审查、交接 |
| 本机精确工具 | PASS：macOS27.0.1/arm64；Git2.56.0、gh2.103.2、Codex0.164.0-alpha.11.1、SDK10.0.402、Node24.22.1、PS7.6.8、Python3.13.17、Docker29.9.2、Aspire CLI13.6.4，实际版本命令exit0 | master/environment.txt、tool-observations.json |
| pnpm隔离 | PASS：node .tools/pnpm/package/bin/pnpm.cjs --version →11.28.8 exit0；官方tarball SHA512匹配，保留全局12.15.0 | master/official-dependencies.json、dependencies.md |
| Python哈希恢复 | PASS：python3 -m pip install --index-url https://pypi.org/simple --only-binary=:all: --no-deps --require-hashes --disable-pip-version-check --target .tools/pythonlibs -r scripts/verification-requirements.txt，exit0；新增cp313 Mac ARM64实际wheel hash，保留Win/Linux hash | 官方依赖JSON，Reviewer独立重新下载内存核验 |
| NuGet锁与真实宿主 | PASS：dotnet restore backend/OntologyPlatform.slnx --use-lock-file真实生成Mac锁；随后--locked-mode、build --no-restore、format --verify-no-changes --no-restore各exit0，MTP4成功/0失败/0跳过 | master/locked-restore.txt、build.txt、tests.txt、format*.txt、native-validation.json |
| 完整组合入口 | PASS：pwsh -NoProfile -File scripts/verify.ps1 -SelfTest -RunNative -RunTests exit0；checker8、doctor2、structured4、环境五变量三状态+清理、ReviewPackage35/0失败，随后真实build/format及MTP4/4 | master/verify-final.txt；Reviewer独立同进程临时快照复验exit0 |
| doctor | PASS：pwsh -NoProfile -File scripts/doctor.ps1 -CheckDocker exit0；默认沙箱曾拒socket，正常权限流程复核，不改ACL | master/doctor-integrated.txt、A/doctor*.txt |
| 固定镜像原生架构 | PASS：四docker buildx imagetools inspect实际exit0，linux/arm64原生索引/子摘要；实际四资源平台linux/arm64，无模拟/换图 | master/runtime-raw-sanitized.txt、runtime-resource-snapshot.json；B/validation.md为转录历史 |
| AppHost/Dashboard/DCP/健康/网络 | PASS：两次dotnet run --no-build --no-restore AppHost实际启动，六HTTP探针200、共享会话网、后端及固定端口只回环；两次stop exit0 | master/runtime-raw-sanitized.txt、runtime-resource-snapshot.json；B/validation.md为转录历史 |
| 四资源持久化 | PASS：既有test-resource-persistence.ps1对专用前缀/容器实际exit0；PG标记、Jena TDB2 URN、RustFS签名S3内容、Keycloak外置库identity重启保持 | master/runtime-raw-sanitized.txt、runtime-observed-validation.json（原始进程输出） |
| 基本Trace查询 | PASS：真实404请求traceparent与Dashboard OTLP返回TraceId/parent/resource匹配；API key仅进程内，查询200，缺key负例401；未关闭认证 | B/trace-query.json、master/runtime-raw-sanitized.txt、runtime-resource-snapshot.json；B/validation.md为转录历史 |
| 资源收尾 | PASS：Master docker ps -a exit0无容器，B六卷及Master两次复验六卷保留；定向lsof exit1/无输出为没有监听，非工具异常；没删卷/其他项目数据 | B/cleanup-observed.json和Master运行器最终实际清理快照 |
| 既有平台保护 | PASS（静态/依赖不变）：Win/Linux及其余三工程五锁逐字节保留；Mac公共图只替换两项平台工具；CI配置无改动 | 依赖记录、Reviewer固定头复验 |
| Linux CI | 已观察3ca9c971实际run40153407207 success；最终任务头及main同Head结果需完成后以manifest.runtimeCi为准，不用旧run冒充新头 | master/ci-progress.json、最终manifest |
| Windows本轮原生、IntelMac、Linux ARM开发宿主 | NOT_RUN；Windows G1历史证据保留；无这些新增宿主锁验收，不把容器ARM当宿主兼容 | portability-matrix.md |
| Web、业务安全/登录、LGTM、生产恢复、G2 | NOT_RUN，未授权，不把最小健康/Trace外推为产品闭环 | 当前授权和任务卡 |

## 失败、修复与剩余边界

新NuGet锁首次缺末尾LF导致静态exit1，仅规范LF且JSON图不变，复验通过。doctor原非Windows路径硬编码linux-x64，A用真实含空格Mac ARM Node夹具先RED再GREEN。完整组合曾在49自测后真实NuGet SDK解析失败exit1：PowerShell把原unset环境恢复成empty；三处用NullString保留unset/empty/value，新回归先有效RED后GREEN，Master和Reviewer均实际同进程组合通过。失败原文保留master/verify-integrated.txt、A/environment-red.txt，未静默丢弃。

B早期旧树SelfTest两次缺parser exit1，外部PYTHONPATH被入口覆盖；中断工具后来发现部分创建了只读解析器链接，Master实际静态复验131文件exit0。B历史前提阻断不改写成原先成功，当前总门禁采用Master真实完整组合与Reviewer独立复验。

构建保留ASPIRE010（当前官方NuGet DCP/Dashboard回退），format诊断0改动/21文件。运行保留未信任开发证书及DataProtection本机profile key未加密警告；本轮只回环开发，不外推生产。Docker/公开包有限漏洞查询未报告已知NuGet漏洞，不代表容器OS完整SBOM/全面供应链或生产安全审计。秘密值不主动写源码、日志、证据或独立秘密文件；Docker/服务内部存储按其机制处理，不能当日常稳定配置或生产备份。

总PARTIAL来自真实平台覆盖边界，不是把未执行项升级为PASS；本轮Mac最低工程验收及独立Review无剩余阻断；未知平台仍NOT_RUN，最终CI结论见manifest。详细许可/官方来源见master/dependencies.md；Mac/Windows回退见开发手册。

## Git、审查与交付

A初始提交a24edf72ab4ea2732af9f4bb507fda7160a3de2a由worker独立提交/推送。环境修复88e6f7a38a97b71c81a57d9c578994cb0ed17865由Master在暂停worker后于同一A树串行完成；Reviewer独立RED/GREEN及Master完整组合复核。B运行由worker完成；收尾工具等待审批中断后明确暂停工具/写入，由Master在独立B分支归档与推送，区分来源。所有权调整写入任务卡，无抢写、强推或覆盖用户更改。

Master分支codex/M0-master；A codex/M0-scripts；B codex/M0-containers。规范化路径见交接。独立审查记录见independent-review.md，原Important环境污染及MinorEOF已修复复核，不把Owner自报当通过。未通过门禁前不进main，最终只由Master集成并推送；保留三树供外部复审恢复。

使用仓库create-review-package.ps1，以明确已提交Base/Head和validation.json生成唯一标准ZIP，再VerifyOnly及独立Reviewer重新打开核对路径/文件/哈希/diff/提交/CI。ZIP仅在原主开发目录artifacts/reviews，排除.git、秘密、工具/依赖/编译缓存、数据库和卷，不提交不上传第三方。精确ZIP路径/大小/SHA256与最终重开结果由外部CLI返回值和最终交付答复给出，避免自引用。

最终停M0关口；只输出M0_MAC_MASTER_READY_FOR_REVIEW后等待人类复审与下一阶段授权，不启动Wave2。

## 原始运行证据补充

B运行转录未被Reviewer作为独立运行批准，Master另以新唯一前缀直接重跑并归档原始脱敏stdout/实际HTTP JSON/退出码。首次m0-mac-observed-17d4d914健康/平台/回环/持久化/Trace均过，但立即检查容器移除遇DCP异步暂态，验收器exit1；原日志runtime-first-cleanup-race.*保留。只为收尾观察加入60秒有界等待，再以m0-mac-observed-b37a079e完整重跑exit0，AppHost exit0，docker ps从四个逐步到零，三个专用卷保留、固定端口无监听。

最终Marker=c0d935b02e854362bc886e679c491881；实际TraceId=df21dc432c6d28b16607dac68578aa9e、parent=5e5f3bf83e8fc263、span=2d988751304145fe、service=infrastructure-api，缺key401/带key200。运行器源码runtime-harness.py和raw输出同提交，原始记录可对照脚本断言与API JSON；不以转录替代原始输出。该固定运行证据已获独立Reviewer通过；最终main的同Head Linux CI由包内runtimeCi记录。

B最终归档头8d4c6e04c43f35d6f3dfa2d2cc4c10e53ac7c292已经独立批准合入Master；三树保留用于本次外部复审及可恢复修正，审查结束再归档，不保留运行容器。原主开发目录已准备校验过的隔离工具，不依赖临时Worktree链接。
