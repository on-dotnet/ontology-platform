# G4-M2-DORIS-01｜TLS最小实施差异申请（2026-11-13）

当前：**已获用户明确批准，实施与真实验证中**，不生成中间ZIP。仍在原会话、原分支、原Worktree；main未更新。

## 已完成与新发现

真实OIDC/UI/API/Worker生命周期8组通过，包括精确sourceId取消/禁用终止、源端撤权、历史目录ACL、轮换和空合成表恢复。当前22项Doris定向测试通过；PG/Web短兼容、120项UI也已有通过原件。两次已知过期证书产品负例失败，不能把整体TLS写为PASS。

`tls-expired-73810d08b90d`独立握手确认FE实际呈现叶证书SHA256 `c740660196413675d5f696917cbb7b8c3152258ec65a77e021fa6f0100ca276d`，有效期2026-11-11T03:06:04Z至2026-11-12T03:06:04Z。OpenSSL使用正确CA及localhost名称拒绝（exit1，certificate has expired）；同一FE、相同CA的MySqlConnector2.6.2原生VerifyFull产品调用却成功。测试结束已恢复原p12 SHA256 `04e28a7f0588b92dc3c9dd42bb9d94f27e9703e1cb4988dca6ad2b11328f1bea`，FE健康与实际产品正常读取1项通过。

[官方2.6.2源码](https://github.com/mysql-net/MySqlConnector/blob/2.6.2/src/MySqlConnector/Core/ServerSession.cs#L1767)在私有CA回退中仅重建链末端证书后清除链错误；结合本机实测，这是当前适用的证书有效期校验缺口。不是未知SBOM项，不用DORIS-LOCAL-01风险接受掩盖。公开源码原件98,997 bytes，SHA256 `4eb5148ad83caddbd285598dedbe94681d8c93b3f3d6ae4a41dd7feea6b6c87b`，位于ignored `artifacts/workflow/G4-M2-DORIS-01/tls-diagnosis/ServerSession-2.6.2.cs.txt`。

## 拟批准的唯一差异

保留MySqlConnector2.6.2和直接FE TLS；连接工厂改用`SslMode=Required`仅为启用驱动公开验证回调，同时移除`SslCa`驱动选项，**由回调对每个实际握手执行完整严格验证**：固定localhost名称错误拒绝、缺证书拒绝、以原私有CA构建叶证书CustomRootTrust完整链、NoFlag、ServerAuth用途、有效期。全部正常和取消辅助连接统一使用该验证器；无明文回退、无代理/全局信任、无独立预检连接替代真实连接验证、不新增依赖。

自建X509Chain禁用AIA/证书下载；驱动在回调前的系统链构建不受这个选项约束，因此本机API/Worker验收同时使用OS级仅loopback出站约束，再验证实际行为，不能仅凭选项宣称整个握手无外联。合成CA没有CRL/OCSP，撤销检查明确NoCheck/NOT_VERIFIED，与原私有CA路径的实际边界一致，不宣称在线撤销通过。缺失CA、异常、未知验证状态均拒绝。初版草案五项离线公证书策略测试exit0；非作者要求补充未知SslPolicyErrors拒绝（已收紧并接入实际握手）。草案为ignored `artifacts/workflow/G4-M2-DORIS-01/tls-diagnosis/StrictCertificatePolicy.cs.txt`，现已按明确批准接入产品。

需要批准的原因：[A–F第4节](conditional-authorization.md#4-d批准-doris_readonly-完整生命周期)明确冻结“VerifyFull”。即使目标是更严格的验证，`Required+完整自定义验证`仍是机制差异，非作者不能自行解除。批准后直接实施并定向验证正常、坏CA、坏SAN、过期、TLS禁用拒绝及取消辅助路径；全部通过才恢复后续产品收口，不逐补丁审批。

## 保持的边界

仅本机合成开发测试；生产Guard、固定目标/范围、资源上限、原依赖身份不变。原证书及任务FE/BE保留待修复验证；新增平台容器/进程已精确回收。源码/门禁/证据收口可继续，TLS相关产品验收停止。此前给reader临时admin角色的负例被自动审批拒绝且未执行，已用仅fixture SELECT角色验证继承拒绝；管理员权限格式仅做实际解析器内存负例，不写为真实管理员授权测试PASS。


## 批准后结果

用户已在本会话明确批准。当前23项定向测试通过；`tls-expired-fa33b74ed4df`实际呈现过期叶证书SHA256 `00e972981f166420e58f0cc3295160b64fd11c107e7de9b5ca62d77e43f4edc3`，OpenSSL拒绝与产品过期拒绝均通过；原p12字节、FE健康及正常目录正例全部恢复。当前继续稳定输入生命周期/资格/审查收口，未解除生产限制。
