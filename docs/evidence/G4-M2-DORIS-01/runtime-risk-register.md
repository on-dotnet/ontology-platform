# 本机合成探针风险与范围（2026-11-13）

最新用户澄清：本机Doris只用于开发合成测试，验收/生产接入用户已有独立Doris集群。本任务不再扩展生产部署或生产恢复演练；保留连接配置源码和既有G4生产限制。以下不是整体安全PASS，不代表既有验收/生产集群已检查。

| 项目 | 原件与适用性 | 本次结论 |
|---|---|---|
| 固定镜像 | 已批准ARM64 manifest/rootfs对应，实际Ubuntu22.04.5、BiSheng17.0.11+11 | 身份核对通过，不换版本/架构 |
| 许可 | 两镜像实际LICENSE-dist.txt、NOTICE及LGPL/GPLv2-CE原件已取得，非作者重算散列；独立本机使用，无制品分发 | 本次未发现禁止该限定使用的条款；完整依赖许可闭包/分发审查NOT_VERIFIED |
| NuGet | MySqlConnector2.6.2官方SHA512、包内身份/net10资产/MIT元数据通过；离线`dotnet nuget verify --all`退出0，仓库签名主体NuGet.org | 离线签名验证PASS；实时撤销NOT_VERIFIED，不混称联网验签 |
| JDK已知候选 | [OpenJDK 2024-07公告](https://openjdk.org/groups/vulnerability/advisories/2024-07-16)将17.0.11列入CVE-2024-21147范围（7.4）；[Ubuntu详细说明](https://ubuntu.com/security/CVE-2024-21147)包含经Web服务API触发，不仅限加载不可信Java代码 | 上游版本命中；BiSheng具体回补及本次输入的可达性NOT_VERIFIED。Gitee两种入口TLS握手超时保留，不能宣称已修复或不受影响 |
| OpenSSL已修项 | 实际openssl/libssl3为3.0.2-0ubuntu1.20；[USN-7786-1](https://ubuntu.com/security/notices/USN-7786-1)的Jammy修订相同 | CVE-2025-9230的发行修订已匹配，不据此断言无其它漏洞 |
| OpenSSL后续项 | [USN-8625-1](https://ubuntu.com/security/notices/USN-8625-1)的握手内存问题、[USN-8678-1](https://ubuntu.com/security/notices/USN-8678-1)的CMS/DTLS等问题修订高于镜像包；[CVE-2026-63072](https://ubuntu.com/security/CVE-2026-63072)说明CMS_decrypt畸形消息路径 | 保留组件风险。FE查询TLS使用JSSE、最短探针不使用CMS/DTLS/外部catalog，仅限定本次路径；不证明整个镜像无风险 |
| JAR组成 | FE可见615个JAR文件名；BE对应lib根目录无JAR，不能推断BE没有Java依赖 | 仅可见索引，不是完整SBOM。全量CVE覆盖、OCI可信发布者签名/attestation仍NOT_VERIFIED |

非作者执行准入结论：现有材料未证明“该BiSheng构建中的未修复缺陷，经本次固定探针输入形成可利用高危链”，按DORIS-LOCAL-01仅放行[最短本机合成探针](execution-probe-plan.md)。固定SQL、随机任务凭据、内部网络/loopback、无生产数据及外部catalog、限额和240秒就绪窗口必须保持。出现明确适用高危链、身份/验签失败或隔离漂移立即停止，不能把风险接受扩大到验收/生产或所有功能链。

公开原件索引见`post-download/originals-index.json`；安全公告原始响应保存在ignored `artifacts/workflow/G4-M2-DORIS-01/security-metadata-20261113-01/02/`及各ledger。每响应上限8MiB、累计上限64MiB，后续读取为先前所有元数据保守预留8MiB，不能把预留值当实际流量。未下载新软件制品、未安装扫描工具，未上传私有数据。

容量核对：截至探针准备前，镜像展开大小之和12,068,903,555 bytes＋去重压缩描述符3,660,429,743 bytes＋任务环境/缓存/过程逻辑文件1,463,445,668 bytes，保守约16.01GiB；其中环境缓存1,425,445,170 bytes、制品缓存31,226,265 bytes，剩余过程文件约6.8MiB，不混称过程产物超过1GiB。该值是制品级保守预算，不是Docker VM物理文件增量实测；后续容器/卷/日志须持续计入25GiB及1GiB过程上限。用户手工下载实际网络字节保持NOT_VERIFIED。


## 2026-11-13新增实测风险：过期叶证书未拒绝

状态：OPEN / 必须修复后才继续TLS相关产品验收。见[tls-validation-delta](tls-validation-delta.md)及tls-expired-73810d08b90d原件。实际FE过期叶证书与独立OpenSSL拒绝均已见证，而MySqlConnector2.6.2+私有CA+原生VerifyFull接受。原服务证书已恢复；此前基础握手、坏CA/SAN通过不能覆盖此缺口。DORIS-LOCAL-01不接受已知适用风险；没有将其当成未知扫描项或标为PASS。


2026-11-13处置：用户已明确批准严格回调差异，产品主/取消连接共享验证器。23项定向及tls-expired-fa33b74ed4df真实过期拒绝、证书恢复正例通过。该缺口在本机批准范围内已缓解；原驱动机制失败历史保留，在线撤销/其它平台/生产仍未核验，最终稳定输入Review待完成。

最终收口：严格TLS在最新输入`tls-expired-64c7c6371966`再次通过真实过期拒绝和原证书恢复读取；24项Doris定向、8组实际生命周期及独立源码审查通过。原生驱动路径的失败保持历史OPEN记录，当前产品已采用获批严格验证器缓解，不代表撤销或生产安全已通过。六份锁仅补末尾LF，包身份/依赖闭包未变。当前保守磁盘约18.80GiB（含完整镜像展开与压缩描述符、任务环境/过程文件和保留卷预留），过程约70MiB；用户拉取流量仍未知。
