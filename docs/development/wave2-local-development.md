# G1 Wave2 本地开发与跨平台回归

本轮使用唯一Aspire模型：正式BFF两实例、Next、专用PG/Keycloak及Alloy/Loki/Tempo/Prometheus/Grafana。7容器、6命名数据卷；原G1-INFRA四基础资源模式仍保留。所有示例身份和秘密只在新建忽略目录中生成，不能复用其他项目卷、Realm或企业身份。

## 精确工具与工程检查

```powershell
pwsh -NoProfile -File scripts/bootstrap-web-tools.ps1
pwsh -NoProfile -File scripts/verify-web.ps1 -Restore
dotnet restore backend/OntologyPlatform.slnx --locked-mode
pwsh -NoProfile -File scripts/verify.ps1 -SelfTest
pwsh -NoProfile -File scripts/verify.ps1 -RunNative -RunTests -SkipWeb
```

前端入口固定Node24.22.1/pnpm11.28.8；归档在提取前核验批准散列，错误即拒绝。全局pnpm12不作为工程入口；只改变本次子进程PATH并恢复。pnpm显式拒绝unrs-resolver安装脚本，实际使用预构建绑定；四项run配置verifyDepsBeforeRun=error，不隐式安装或更新锁。只有显式Restore执行冻结锁和项目store。SkipWeb仅表示Web已独立执行或隔离checker fixture，不意味着Web通过。

## 隔离运行

首次使用Python3.11+（Mac/Linux命令为python3，Windows为python）执行：

```text
python3 scripts/acceptance/wave2-runtime.py prepare
python3 scripts/acceptance/wave2-runtime.py core --runtime-file <prepare返回的.tools/security路径>
```

core就绪后，在另一个终端运行bootstrap；再正常停止core，随后full使用同一私有runtime和卷：

```text
python3 scripts/acceptance/wave2-runtime.py bootstrap --runtime-file <同一私有runtime>
python3 scripts/acceptance/wave2-runtime.py full --runtime-file <同一私有runtime>
```

先完成Web build；全栈使用已构建Next。prepare不覆盖已有秘密或证书，bootstrap只创建新随机Realm，运行文件0600/目录0700。PFX只保护共享keyring，不安装系统信任。Mac使用.NET临时keychain导入，其他平台使用EphemeralKeySet；生产必须显式HTTPS、AllowedHosts和可信代理，缺失或通配Host配置失败关闭。禁止把runtime、Cookie、token、证书、卷和原始认证trace提交或打包。

公共BFF15100、第二实例15101、Next内部15300、Keycloak18080、PG15432；Alloy14328/14327、Loki13100、Tempo13200、Prometheus19095、Grafana15330。容器端口和Next实际只绑定回环，API外部入口通过localhost。Grafana随机密码只在本轮私有配置/进程中使用；生产运维入口不在此开发部署中承诺。

## 真实验收

```text
python3 scripts/acceptance/test-governance.py
python3 scripts/acceptance/verify-openapi.py
python3 infra/security/verify-oidc.py --runtime-file <同一私有runtime>
python3 scripts/acceptance/verify-api-restart.py --runtime-file <同一私有runtime>
python3 scripts/acceptance/verify-alert.py
python3 scripts/acceptance/verify-persistence.py --runtime-file <同一私有runtime>
python3 scripts/acceptance/verify-dependency-fault.py --runtime-file <同一私有runtime>
```

test-governance创建临时PG+Keycloak，随机秘密仅内存/忽略文件，退出删除其专用容器。主开发KC使用PG专库；CI的临时KC只用于真实PAR网络测试，不把它当作主开发持久化验收。完整安全套件需要这两个真实前提；普通native工程检查缺前提明确NOT_RUN，强制integration CI执行全部测试。

API重启验证先在内存保留真实Cookie，再由Master受控替换唯一AppHost/API进程，重启就绪后按Enter继续；不把Cookie写盘。告警脚本仅SIGSTOP/SIGCONT当前checkout的两个精确API；容器持久化脚本仅重启记录且再次校验专用卷的7个名字，finally恢复数据库故障。请勿在这些受控生命周期检查期间并行手工改栈。数据库readiness等待真实命令超时，测试客户端必须留足时间；不能把客户端提前超时当作服务器503。

真实浏览器runner通过进程环境PLATFORM_TEST_RUNTIME指向本轮私有配置，执行`node apps/web/scripts/run-oidc-tests.mjs`。它使用安全reporter、不留error-context/trace/video/HAR；截图仅登录后的合成资源页面。UI夹具5项与真实OIDC2项分开，fixture不代表登录通过。

观测查询与中文运维说明见[观测手册](observability.md)，身份/证书轮换边界见[安全手册](security.md)，设计系统见[Web手册](web.md)。日志先脱敏再输出；同Trace查询、两实例先分序列再聚合，不以Running代替数据。

## 跨平台范围

Mac ARM64及Linux ARM64容器已实测；Ubuntu x64同Head CI提供实际Linux编译/Web/PG+KC安全回归。Windows原生和Intel Mac没有本轮主机，仍NOT_RUN；其回归使用上述PowerShell入口及精确锁，原AppHost win/linux/osx锁均受锁恢复验证，不把锁恢复当原生产品运行。不要改全局PATH、默认SDK、系统Docker或GitHub规则来绕过缺前提。
