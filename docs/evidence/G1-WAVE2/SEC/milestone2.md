# SEC 第二里程碑 · PARTIAL

日期：2026-10-25；Owner=SEC；分支 `codex/G1-SEC-001`。父提交 `c87bb737a0959a597ed12e85c3d35142b7a280b0` 已包含 Master 的 `d43be715` EF graph 修订。本次不修改根CPM、锁、solution、AppHost、合同或迁移，不进入main，不另建ZIP；独立审查/整合由 Master 安排。

## 已观察与修复

- 既有 `http-red.txt`：macOS PFX 的 EphemeralKeySet 不受平台支持；现按平台选择 DefaultKeySet 并注册停机释放，不安装系统信任。
- 既有 `http-red-routing.txt`：保留前缀未知路由进入Next；现正式.NET保留 catch-all 返回404。
- 真实 Kestrel 测试覆盖匿名/坏Cookie/伪造角色、错误回调/恶意returnUrl/转发头、Production探针与PG故障、Host白名单、保留前缀；另有2项纯授权边界测试。
- Bootstrap 新增3项无凭证本地测试：真实HTTP重定向不跟随、秘密输出拒绝源码树、origin拒绝路径/query/fragment/用户信息。RED记录1失败及缺少验证函数；GREEN 3/3。只使用临时本地服务器和固定无效合成标记。

## 真实命令记录

命令在独立SEC树运行，.NET10.0.402、Python3.13.17、PowerShell7.6.8，macOS ARM64。

| 命令 | 结果 | 原始输出 |
|---|---|---|
| `dotnet restore backend/tests/OntologyPlatform.SecurityTests/OntologyPlatform.SecurityTests.csproj -p:RestorePackagesWithLockFile=false` | FAIL exit1：既有ServiceDefaults锁触发NU1005；SEC新图已生成 | milestone2-restore.txt |
| `dotnet restore backend/src/ServiceDefaults/OntologyPlatform.ServiceDefaults.csproj --locked-mode` | PASS exit0，未编辑锁 | milestone2-servicedefaults-restore.txt |
| `dotnet test --project backend/tests/OntologyPlatform.SecurityTests/OntologyPlatform.SecurityTests.csproj --no-restore` | PASS执行项7/7，另1项PG NOT_RUN，exit0；不表示完整SEC通过 | milestone2-security-tests.txt |
| `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s infra/security -p 'test_*.py'` | PASS exit0，3测试 | bootstrap-green.txt |
| `dotnet format ... --no-restore --include <3个SEC文件>` | PASS exit0，仅3个SEC文件 | milestone2-format.txt |
| `pwsh -NoProfile -File scripts/verify.ps1 -SelfTest` | PASS exit0，含ReviewPackage35项；原生/FE未在此命令执行 | milestone2-selftest.txt |

第一次selftest因旧临时log的CRLF/空文件以及`password = secrets.token_urlsafe(...)`被有限扫描误判而FAIL。只归一化本Owner证据文本；运行时随机变量采用明确generated命名，没有硬编码秘密；复验输出保留。原始日志未含真实凭证，归档txt仅统一LF/移除尾随空白，不删除失败。

## 未执行与集成条件

PG未注入：`SharedEncryptedTicketRevocationAndExpiryUsePostgresFacts`明确NOT_RUN，不冒充PASS。真实OIDC登录/CSRF/退出重放/双实例HTTP Cookie、PG重启持久化、FE和OBS纵向联调、同Head Linux CI、独立Reviewer仍待Master统一栈。锁定新工程restore未完成，不声称通过。当前CI=NOT_VERIFIED。证书轮换旧私钥保留策略见安全手册，生产多证书解密未实现/未验证。禁止将本提交当Wave2全量PASS。
