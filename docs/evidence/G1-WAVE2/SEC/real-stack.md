# SEC 真实 Keycloak / 双 API / PG 验收增量

状态：**PARTIAL（本节已执行项PASS；浏览器/重启/CI/独立复审待总集成）**。日期2026-10-25。分支前置`df4b021acfafe183f7121451379a6f4636a3eb12`。本轮仅SEC owned_paths；未更改Keycloak已有配置、Secure策略、PAR行为、迁移、公共合同、锁或AppHost。Master维护统一栈与本轮新建专用卷，所有身份/密码均本轮合成随机。

## 前提与运行版本

真实统一栈回环端口：BFF15100/15101、Keycloak18080、PG15432；Keycloak26.8.1、PG18、.NET10.0.402、Python3.13.17，macOS ARM64宿主与Linux ARM64开发容器。Master候选代码快照由总集成证据固定；此次HTTP协议执行时正式服务尚无新OnPush日志增量，另用SEC正式源码的独立Kestrel真实推送验证新增事件，不冒充统一栈已重启更新。

私有runtime及realm文件只通过显式参数/进程环境在内存消费，不读取旧凭证或旧卷。PG连接在进程内构造注入，测试输出在写入证据前替换本轮已知秘密；不输出命令环境、Cookie、token、用户名密码、code/state/nonce、回调URL或响应正文。协议驱动只输出固定安全检查名、合成身份标签、HTTP状态。

## 故障与修复证据

1. Master首次驱动在前端URL检查code/nonce/state失败（master证据保留）。官方.NET10.0.13默认PAR在推送后仅保留client_id/request_uri，故障在旧harness假设。新增PAR分支及安全OnPush事件；不禁用PAR，官方框架正常推送、认证和回调。
2. `oidc-par-first.json`：PAR引用观察通过，但登录页面400。安全诊断定位KC Secure AUTH_SESSION_ID/KC_RESTART已存但urllib在HTTP localhost不发送。驱动限定批准loopback origin的浏览器等效cookie策略，负例拒绝其他端口/域；不修改产品或KC安全选项。单元RED/GREEN见cookiepolicy-red.txt/par-python-green.txt。
3. `oidc-par-second.json`：真实登录、角色/作用域与CSRF拒绝均已通过，旧驱动精确字符串比较误拒框架`no-cache, no-store`。修为指令集合判断，没有删除no-store检查。
4. `oidc-par-third.json`：最终真实五身份全程PASS，310项检查、零失败。保留前两次失败，不回写历史证据。

## 已运行验收

| 运行项 | 实际结果 / 证据 |
|---|---|
| `PYTHONDONTWRITEBYTECODE=1 python3 infra/security/verify-oidc.py --runtime-file <本轮私有runtime>` | 最终exit0，viewer-a66/viewer-b66/no-role-a54/operator-a66/auditor-a58，共310PASS；oidc-par-third.json |
| 匿名/坏Cookie/错误回调/伪Forwarded | 每身份独立真实请求，分别401/401/400/400，ProblemDetails、no-store、trace/correlation检查 |
| OIDC登录/最小身份/双API | 每身份真实Keycloak password form→正式callback，PAR reference；HttpOnly/Lax Cookie、批准身份字段、组织厂区、同一Cookie跨实例身份一致 |
| 资源与审计权限 | viewer/operator自身200/跨厂403/未知404；no-role403；auditor资源403、审计200且仅org-demo/site-a、非法limit400；其他角色审计403；资源响应带真实审计ID |
| CSRF/真实注销/旧Cookie重放 | 每身份无CSRF403；真实Antiforgery字段注销302→Keycloak→signout callback；恢复旧Cookie后两实例/me均401 |
| `dotnet test --project backend/tests/OntologyPlatform.SecurityTests/OntologyPlatform.SecurityTests.csproj --no-restore`（显式注入PG和Keycloak本轮配置） | exit0，**11/11 PASS，0跳过**；real-pg-par-tests.txt |
| 正式OnPushAuthorization真实网络验证 | 独立正式Kestrel向本轮真实KC发PAR，安全内存捕获确认五布尔全True；302有request_uri无state/nonce；不HandlePush/SkipPush、不替换网络。单元合成标记不入日志；par-csharp-red.txt为新增事件RED |
| PG票据/共享keyring/审计 | 两个独立服务容器用同测试共享证书与keyring，无内存会话缓存；真实PG密文不含合成token、最长30分钟、撤销后不可读且renew不复活、过期不可读、登录/注销审计实际存在。清理仅测试创建的会话与合成审计；不冒充OIDC或容器重启 |
| Python离线/helper测试 | exit0，8/8；含bootstrap真实本地HTTP/0600文件正例、目标/redirect/form边界、PAR引用、Secure-localhost例外范围；par-python-green.txt |
| format / SelfTest | 实际输出分别par-format.txt / real-stack-selftest.txt；最终状态以输出为准 |

## 未运行及边界

浏览器UI/SSR/无障碍/Console=NOT_RUN（由FE独立验收），PG/API服务或开发容器重启=NOT_RUN（由Master统一编排），Windows/Intel Mac原生=NOT_RUN，同Head Linux CI=NOT_VERIFIED，独立Reviewer=待复审。证书多证书解密轮换仍未实现/未验证，不能将当前持久keyring成功当作轮换成功；生产部署/审计合规/G2不在本次范围。当前SEC提交不自行进入main、不开第二ZIP。
