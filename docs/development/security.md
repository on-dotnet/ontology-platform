# Wave2 安全入口运行手册

状态：PARTIAL；正式契约见[平台公共契约](../contracts/g1-platform-contracts.md)。此文档只覆盖 G1 Wave2 本地合成身份、PG 服务器会话与 API 安全入口，最终集成、迁移及 CI 由 Master 验证。

## 启动前提

正式宿主是 `backend/src/Hosts/OntologyPlatform.Api`，与 InfrastructureApi 技术探针独立。通过进程环境或不入 Git 的私有配置注入以下键；不要把秘密写进命令参数、日志、截图、源码或审查包。

| 配置键 | 用途 |
|---|---|
| `Security__Authority` / `ClientId` / `ClientSecret` | 专用 Keycloak realm 与 confidential client，code + S256 PKCE |
| `Security__PublicOrigin` | 固定外部 BFF origin，默认本地测试 `http://localhost:15100` |
| `Security__KeyRingPath` | 两实例共享的持久 DataProtection 目录，0700 |
| `Security__CertificatePath` / `CertificatePassword` | 本轮随机生成的 PFX，0600，保护 keyring；不安装系统信任 |
| `Security__HealthKey` | 至少24字符的随机内部探针秘密 |
| `ConnectionStrings__governance` | 本轮专用 PG 数据库，带凭据；禁止生产连接 |
| `Web__Origin` | 可信 Next 内部回环地址，浏览器不感知 |
| `AllowedHosts` | 显式主机列表，禁止空值或通配 |
| `Security__TrustedProxies__0` 等 | 可选明确代理 IP；默认拒绝转发头 |

表内缩写 `ClientId` 等均位于 `Security__` 前缀下。生产仅 HTTPS，Cookie Secure=Always，不允许开发 seed 或启动迁移。开发 `Governance__ApplyMigrations=true` 和 `Governance__SeedDevelopmentResources=true` 是两个显式独立开关；迁移文件与接线由 Master 单写。第二实例使用相同 PublicOrigin、ApplicationName、PG、PFX 与 keyring，监听不同端口。

缺配置、错误证书或入口不可信时启动失败；PG 不可用时 ready=503，live 仍可用。探针在生产也存在，必须携带运行时 `X-Health-Key`，错误凭据401；响应不返回连接详情。

## 专用 Keycloak bootstrap

只对本轮新建的独立 Keycloak 执行 `infra/security/bootstrap-keycloak.py`。管理员用户名、随机密码通过 `WAVE2_KEYCLOAK_ADMIN_USERNAME` / `WAVE2_KEYCLOAK_ADMIN_PASSWORD` 进程环境注入；不从旧卷或用户凭证读取。示例只展示没有秘密的参数：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 infra/security/bootstrap-keycloak.py \
  --keycloak-origin http://localhost:18080 \
  --public-origin http://localhost:15100 \
  --runtime-output .tools/security/identities.json
```

该 helper 创建随机 `wave2-` realm 与 confidential client，只创建新的五个合成身份；遇既有输出立即停止，不更新旧 realm/身份。密码与 client secret 每次随机，保存在当前 checkout 被忽略的 `.tools/security/**`，父目录必须0700、文件0600，输出只含状态/realm/合成用户名。禁止输出到源码目录；请求禁用环境代理且不跟随任何重定向，远端错误正文始终抑制。origin 仅接受无路径、query、fragment、用户信息的 HTTP localhost/127.0.0.1。失败只输出类别或 HTTP 状态；如 realm 创建成功但本地持久写失败，由 Master 核查本轮隔离资源，禁止打印远端正文或重新复用旧秘密。

身份为 viewer-a（site-a）、viewer-b（site-b）、no-role-a、operator-a、auditor-a；用户名带 `wave2-` 前缀。管理员仅供 bootstrap，不能用于产品登录。保存本轮私有 runtime 文件供重启复用，不在重启时重建 realm 或改变密码。

## 会话、安全响应与证书轮换

Cookie 只保存受保护的随机 PG 会话引用，HttpOnly、Lax、绝对30分钟、无滑动续期。OIDC token 保留在 PG 加密服务器票据中，不进入 `/me`、HTML、JS 或 localStorage。资源授权按批准角色及 organization/site 双重过滤，请求头不能授予权限。读取/拒绝及登录/注销审计写入 Governance PG；数据库失败返回通用503，不能声称审计已成功。

退出采用原生 form POST `/auth/logout`，携带内置 `__RequestVerificationToken` 隐藏字段；非浏览器客户端也接受 `X-CSRF-TOKEN`。禁止 fetch 跟随跨源 OIDC 退出。撤销 PG 会话与注销审计事务提交后旧 Cookie 不可重放。错误统一 ProblemDetails 与 trace/correlation ID，未知 `/api`、`/auth`、`/health`、`/openapi` 前缀返回404，不能进入 Next。

两个实例必须设置相同 `OntologyPlatform.PlatformBff.v1` ApplicationName 并共享证书加密持久 keyring。macOS 的 .NET PFX 导入采用 DefaultKeySet（临时 keychain，证书释放时删除）；其他平台采用 EphemeralKeySet，不安装信任。进程停机释放证书；测试临时证书和 keyring 随测试删除。轮换前保留旧私钥证书和既有 keyring，待所有旧密钥/会话保留期结束后再移除；当前实现仅加载单一保护证书，多证书解密轮换及生产保留策略仍需后续专项实现和验证，不能直接替换证书并声称旧票据持续可读。

框架认证、HTTP客户端、EF 与包含 query 的默认请求日志被抑制，自定义日志只记录路由模板、状态和关联ID。禁止 Playwright 登录 HAR/trace、Cookie、token、code/state、身份原始声明入证据；只保存检查结果、脱敏响应与计数。

## 复验与当前边界

```sh
dotnet restore backend/tests/OntologyPlatform.SecurityTests/OntologyPlatform.SecurityTests.csproj -p:RestorePackagesWithLockFile=false
dotnet restore backend/src/ServiceDefaults/OntologyPlatform.ServiceDefaults.csproj --locked-mode
dotnet test --project backend/tests/OntologyPlatform.SecurityTests/OntologyPlatform.SecurityTests.csproj --no-restore
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s infra/security -p 'test_*.py'
pwsh -NoProfile -File scripts/verify.ps1 -SelfTest
```

SEC 分支尚无 Master 生成的新工程锁时，第一条在已有 ServiceDefaults 锁处会报 NU1005，但已生成新 SEC 项目 assets；第二条恢复既有锁图。Master 交付全锁后应统一改用真实 `--locked-mode` restore，此分支临时过程不代表受锁恢复PASS。

PG 测试仅通过进程环境 `G1_SEC_PG_CONNECTION` 接受本轮专用连接，且要求 Master 先应用迁移；缺少前提明确 Inconclusive/NOT_RUN。它以两个独立正式宿主容器的真实票据存储器验证共享加密 keyring、PG密文、撤销/过期及PG审计，合成票据不冒充真实 OIDC 登录。真实 Keycloak 浏览器闭环、HTTP双实例Cookie、过期/重放/CSRF、资源作用域、PG重启与全链遥测由统一栈继续实测。

Windows 原生与 Intel Mac 本轮 NOT_RUN；Windows 可在固定SDK下运行相同 PowerShell selftest、受锁 restore 和 `dotnet test --project ...`，不得将 ARM64 Mac 成功当作跨平台通过。

## HTTP 协议验收驱动

`infra/security/verify-oidc.py --runtime-file <本轮私有runtime.json>` 消费 Master 生成的 `realmFile`，只对明确的 localhost 15100/15101/18080 origin 发请求，每次重定向和登录 form action 都重新检查目标。它使用真实 Keycloak 登录、PKCE/state/nonce challenge、回调、五身份角色/厂区、双实例Cookie、CSRF、注销与重放、真实API审计读取，输出仅有固定检查名/合成身份标签/状态码，不输出响应正文、密码、Cookie、token、回调URL或异常详情。此协议驱动不是浏览器交互验收，SSR/无障碍/Console仍由FE Playwright复验。无真实栈运行输出时明确NOT_RUN。

代理日志也必须抑制：YARP 默认 Info/Error 正文可能包含完整上游 URI；正式 API 过滤 `Yarp.ReverseProxy` 并仅使用自定义路由模板/状态/关联ID安全日志。`ProxyQueryNeverEntersLogBody` 经真实HTTP与内存日志捕获验证，测试只用无效合成query标记。
