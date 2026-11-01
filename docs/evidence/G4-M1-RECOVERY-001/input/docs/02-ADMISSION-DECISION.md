# 镜像准入关口修订：原合同差异及准确审批边界

本文件**仅提交审批建议**。用户批准前，`G4-M1-CONNECTION-001` 的旧门禁照旧生效，任何拉取/运行都未获此文件授权。

## 原问题

先验地要求“下载前完成精确镜像全部分发组件许可证据”与“只能从镜像层生成实际安装软件包清单”不兼容，Keycloak ARM64/ASP.NET ARM64 缺远程完整 SBOM，`NOASSERTION` 和不准确的包版权 URL 无法单靠 index 补齐。上轮做了12次 manifest 查询、超时的 SPDX便利查询、正确地停止镜像下载。因此本轮不是再次“多查几次官网”，而是明确授权生成实际镜像 SBOM 所需的最小受控取证操作。

## 三条互相独立的门禁

| 门禁 | 强制条件 | 何时执行 | 是否意味着可商用分发 |
|---|---|---|---|
| A：OCI 来源准入 | 官方发布者、固定 digest、目标平台匹配、顶层项目许可证、明显禁止性条款、预算/所有权 | 任何层下载前 | **否** |
| B：研发内部运行准入 | SBOM/实际层证据、许可状态与风险表、非作者 Review、无已知冲突；GREEN或已获批准的 AMBER-A1 | 下载后、任何容器运行前 | **否** |
| C：正式商业发布准入 | 完整部署镜像及应用依赖SBOM、版权/NOTICE、分发义务、依赖及模型权重许可、漏洞/签名/法务裁决 | G8 分发/交付前 | **是，需实际验收** |

**AMBER-A1 的默认判断和含义**：仅源码/许可证元数据部分未知，未发现明确限制内部测试；可在明确批准“内部、纯合成、不分发”的情况下继续本轮开发，在报告中继续保留 `LICENSE_PARTIAL`。不能把默许开发测试解释为对用户下游商业分发的法律保证。AMBER-A2/RED停止并申请人工决策。

## 镜像与预算白名单

从 `evidence/image-candidates.json` 直接绑定官方 index 和 per-platform digest：

1. `postgres:18.6-trixie` index `sha256:3a4264520e121176619f54ff867d12774bc81e95e7b84db58d63bccdb6144b81`
2. `quay.io/keycloak/keycloak:26.8.1` index `sha256:3f3c5f8e03c614774b4bd9173b88391fefa4153bfc010d8012d59ad825377332`
3. `mcr.microsoft.com/dotnet/aspnet:10.0.13` index `sha256:8af87eba5e7cdafb1514d7388be287365da97c132509e84dfe252ffd552398ca`
4. `node:24.22.1-trixie-slim` index `sha256:89c5244bc22a9bc3287d89ebc7e49b9cb5bb84cd40e6175ac3421d5a9f68b95a`

仅 Mac `linux/arm64` 精确 payload 可在用户明确授权后拉取。ARM64 四镜像官方观察的压缩字节合计 `600,460,317`；层复用后 manifest estimate `570,246,821`，**不是下载必然值/磁盘实占**。上限仍为先前用户批准的 3 GiB 镜像下载、3 GiB 任务卷、6容器/6GiB内存。不能增加 GPU 或公开端口、重启全局Docker。下载前检查当前磁盘预算，执行时跟踪真实变化；任何超出停止。默认不下载 AMD64 层、不替换镜像摘要。

### 合规证据输出

每镜像记录：input source + digest + platform + image ID、scan tool/version、SBOM hash/size、purl与许可矩阵、NOTICE/copyright、NOASSERTION和许可证文本缺口、明确禁止性或分发义务、已知漏洞/签名实际核验状态（NOT_VERIFIED不得写无风险）、Reviewer verdict、能否仅合成内测、G8必须补齐的项。

可用工具官方参考：

- <https://docs.docker.com/reference/cli/docker/scout/sbom/>
- <https://docs.docker.com/scout/how-tos/artifact-types/>
- <https://docs.docker.com/scout/how-tos/view-create-sboms/>
- <https://docs.docker.com/scout/policy/>

这些文档说明：registry/index 可能有随镜像的 SBOM/构建证明；缺失时可扫描**实际镜像**生成 SBOM，`registry://` 远程扫描也可能获取层。不要将“项目许可证文本”当作完整OS包/运行时许可；也不要将 “有NOASSERTION” 推断成非法使用。

### 确切历史问题台账

- `postgres`、`node` 有 SPDX，但部分 `NOASSERTION`，别把单包未知误写成整个镜像未授权。
- `keycloak` 仅见 SLSA而无确切JDK/RPM完整第三方列表；已有 `third-party-notice` 覆盖部分但非完整。
- `aspnet` 仅见 Notary产物、config标 Ubuntu24.04 & ASP.NET10.0.13，未给完整运行时组件版权清单。
- `tzdata` / `libxcrypt` 特定包URL 404只说明来源获取未成功，不能因为邻近版本版权相似就伪装 exact。
- Docker Scout不可用就拒绝未批准工具安装，不能因急于赶工而随便 `curl | sh`。
