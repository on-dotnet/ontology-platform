# B 运行验证与交接记录

状态：**PARTIAL，等待最终独立 Review、Master 集成及真实远程 CI**。本记录中的单项 PASS 不代表 G1 全阶段通过。日期：2026-10-23。

## 隔离与提交

- Worktree：C:/Users/Administrator/.codex/worktrees/g1-infra-aspire/ontology-platform；分支 codex/g1-infra-001-aspire。
- B BaseSha：968ab2a3378427cc4f2612ddb1dbb1b60b5ce9e2。修改前树干净，fetch 后与当时 origin/main 一致。普通沙箱写 FETCH_HEAD 被拒，获批提升后 fetch exit0。
- 初始 DRAFT：e8c0c3e，已普通 push 到 origin/codex/g1-infra-001-aspire。Master 共享配置7ba3839合入B为66a32a4，无冲突；未修改根单写者文件。后续实际 HeadSha 由本记录所在提交及 Master 总交付记录固定。
- 仅 B owned_paths 交付；四工程接入根 solution/CI、main 集成 SHA 和唯一标准审查 ZIP 由 Master 完成。

## 工具、恢复、编译与测试

所有 .NET 命令用 Master 已核实 SHA-512 的隔离 SDK10.0.402，进程 DOTNET_CLI_HOME/NUGET_PACKAGES 指向项目 .tools；没有降低精确版本或改机器 PATH/默认SDK。

| 命令/核验 | 实际结果 |
|---|---|
| restore AppHost csproj | exit0，真实恢复 AppHost/ServiceDefaults/API |
| restore InfrastructureTests csproj | exit0，真实恢复测试SDK及传递依赖 |
| restore AppHost --locked-mode | exit0，Windows真实锁图 |
| restore AppHost -p:NETCoreSdkRuntimeIdentifier=linux-x64 | exit0，仅生成Linux SDK工具包锁图 |
| restore AppHost --locked-mode -p:NETCoreSdkRuntimeIdentifier=linux-x64 | exit0，仅恢复验证；没有声称Linux实际构建运行 |
| 再次 restore AppHost --locked-mode | exit0，切回Windows实际恢复资产 |
| restore InfrastructureTests --locked-mode | exit0 |
| build AppHost --no-restore | 最终exit0，0错误，1个已保留ASPIRE010警告；依赖API/ServiceDefaults编译成功 |
| build InfrastructureApi --no-restore | exit0，0警告0错误 |
| test --project InfrastructureTests csproj --no-restore | 最终exit0，4通过/0失败/0跳过，2.720秒 |
| format AppHost csproj --no-restore --verify-no-changes | exit0，有工作区加载警告，未隐藏 |
| format InfrastructureTests csproj --no-restore --verify-no-changes | exit0 |
| verify.ps1 -SelfTest | 最终静态+8自检exit0；原生目标仍由Master接线，不能将该脚本的旧NOT_RUN覆盖本表独立真实测试 |

AppHost隐式引入平台专用Dashboard/DCP工具包。锁文件采用packages.win-x64.lock.json和packages.linux-x64.lock.json，由NuGetLockFilePath按NETCoreSdkRuntimeIdentifier选择。其余三个工程各一份packages.lock.json，共五份真实生成锁文件。当前明确支持win-x64及linux-x64；其他平台未生成锁，不冒称支持。Windows上的Linux恢复不替代Ubuntu CI。

测试红阶段初写时精确SDK尚缺，NOT_RUN；未将缺项目/编译错误冒充预期断言失败。四项真实测试覆盖开发健康/非业务404、依赖不健康时就绪503但存活200、生产环境默认不公开探针、逻辑服务发现访问真实回环宿主。CS1591之外的私有成员、局部中文说明、成员空行已由独立只读Reviewer专项检查，初轮未发现Critical/Important源码问题。

## 容器与真实重启

三预构建镜像pull均exit0。Jena Docker build exit0，Apache官方tar.gz在镜像构建中sha512sum --check --strict返回OK。版本及不可变摘要见dependencies.md。

最终资源通过AppHost实际启动，使用独立测试卷前缀ontology-platform-g1-01297fcc及内存随机秘密。最终镜像引用已经固定SHA-256。全部HTTP探针在重启前后返回200：

- API /health和/alive；
- Fuseki /$/ping；
- RustFS /health/ready；
- Keycloak独立管理端口/health/ready。

实际docker后端映射均为127.0.0.1。Get-NetTCPConnection检查固定代理端口13030/15080/15432/18080/19000/19001/19090及dashboard15888，均仅127.0.0.1和::1监听。具体运行时摘要见[runtime-summary.json](runtime-summary.json)。

test-resource-persistence.ps1最终实际执行PASS：校验三个命名卷挂载；在专用schema写PostgreSQL随机标记，在TDB2写测试URN，以SigV4在独立S3 bucket写对象；重启四个本任务容器后校验同一标记、URN和对象内容；Keycloak管理就绪恢复且外置库同一引导身份非秘密ID保持一致。结果随机标记186fdcea83b644fb86ede63215b56a5a不是凭证。此验证不涉及产品业务登录或生产数据。

收尾已停止最终AppHost及四个测试容器；最终实例名postgres-vkqrnzvy/fuseki-yxbrxqxe/rustfs-nbsjexqs/keycloak-pkppjgdd，测试卷保留未删除。其他项目容器持续运行，未触碰其数据。旧失败尝试的四个测试容器已按明确实例名移除，未删卷。测试随机秘密只在验证进程内存使用，未写仓库或打包；测试卷不是日常开发卷，不可把随机秘密失效后的卷误当可复用开发配置。

## 真实基本遥测边界

AppHost运行日志实际显示Dashboard15888和OTLP/gRPC14317启动，保留[脱敏应用日志](apphost-sanitized.txt)。未打开Dashboard、未读取其令牌或调用受保护认证API。

独立最小API以Console IncludeScopes=true启动，发送公开固定traceparent的GET /g1-infra-unknown，实际404；请求日志scope包含相同TraceId，见[关联结果](trace-correlation.json)与[请求日志](trace-correlated-log.txt)。这是实际ASP.NET请求活动和日志scope关联PASS。没有新增产品端点。

Dashboard ingest、OTLP全链传输/可检索性与完整LGTM仍NOT_VERIFIED/NOT_RUN；不以四个HTTP测试或控制台关联取代这些能力，完整OBS不在授权内。DCP在本机报告Windows Unix-domain-socket日志连接警告并回退控制台；资源与健康检查实测可用，未掩盖该运行限制。

## 失败、修复与安全边界

1. 首次ServiceDefaults编译CS1061：已通过恢复包XML定位缺少OpenTelemetry根命名空间导入，补导入后真实复编通过。
2. 首次HTTP开发profile触发Aspire启动配置验证：显式声明ASPIRE_ALLOW_UNSECURED_TRANSPORT=true，仅本机明文开发传输；保留仪表盘默认认证，不改机器证书信任。
3. 首次Fuseki反复退出：实际日志指出TDB2目录不存在，新增非root幂等entrypoint创建卷内目录，重建并复验通过。
4. 首次psql探针要求认证：改为Docker子进程PGPASSWORD环境注入，命令行不含密码，不读现有认证文件。
5. 一次S3探针被PowerShell本地Authorization头校验拒绝，原异常回显本次临时访问标识及签名，未回显secret key。立即停止并移除本次测试容器，轮换两个临时S3凭证；脚本增加AWS头兼容和通用脱敏异常。旧原异常未持久化，证据不含其原值，最终签名写读/重启复验PASS。
6. 一次编译与正在运行的AppHost并行，Windows锁定exe导致MSB3021/3027；停止本次宿主后重新编译PASS。该失败如实记录，不算源码错误。
7. 静态检查发现CRLF/末尾换行问题，统一B所属文本LF并复验PASS。
8. ASPIRE010保持可见：使用官方NuGet Dashboard/DCP回退，不安装CLI，不全局抑制警告；当前授权内资源启动已实测。CLI专有特性未验。

真实NuGet漏洞检查对AppHost和测试工程分别执行list <csproj> package --vulnerable --include-transitive --no-restore，均exit0，源https://api.nuget.org/v3/index.json报告当前无易受攻击包。锁图与SDK共112个包身份的许可元数据登记见dependency-lock-inventory.json。此检查不是全面安全保证；容器CVE扫描、OS层SBOM/复合许可、生产安全/备份恢复均NOT_VERIFIED。

CI实际run/URL/commit结论及最终main集成尚由Master验证，本树标NOT_VERIFIED。没有启动SEC/FE/OBS/G2或付费模型。等待独立最终Review和当前关口交付，不自动进入下游。

最终证据脱敏核验：在仍持有本次秘密的验证进程中，对所有B证据文件逐值检查当前四个随机开发秘密，0命中，仅输出PASS而不输出原值。独立Reviewer建议补充卷前缀无效时ArgumentException中文XML，已补齐。该有限检查不宣称全面防泄露。
