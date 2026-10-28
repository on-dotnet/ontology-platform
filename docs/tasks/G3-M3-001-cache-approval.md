# G3-M3 E0-A：新增官方缓存Action审批（APPROVED）

## 具体申请

仅在CI新增GitHub官方MIT许可`actions/cache/restore`与`actions/cache/save`，版本v6.1.0，固定commit `55cc8345863c7cc4c66a329aec7e433d2d1c52a9`（tag已通过GitHub API核对）；LICENSE blob `a426ef259d6c5d705e9c1405075c3b318093c65e`，API识别MIT；node24运行时。只使用仓库现有GitHub Actions cache配额，不启用额外付费容量、不修改账单/预算/组织设置，不能确认配额时停止缓存写入并报告BLOCKED。人类本会话明确回复“批准上述精确范围”（2026-10-28）；仅批准此处两个Action精确SHA/现有已含配额/无发布权限。

用途：保存canonical Fuseki的经过校验构建产物/官方源包，在相同输入、平台的另一个全新runner恢复。所有缓存视为不可信提示，校验输入fingerprint、归属、平台、archive hash、image ID及标签；源包始终校验已冻结SHA512，损坏拒绝并有界冷重建。键包含版本/JRE摘要/完整context/helper/平台，禁宽泛restore-key。CI用两个独立Run记录cold/hit，不能将同run reused冒充跨run命中。

## 权限、发布和供应链

保持`permissions: contents: read`，不添加packages:write/actions:write，不需要PAT/长期secret。缓存传输由官方Action使用GitHub运行时令牌，项目工具不读取或输出令牌。无GHCR/公开或私有镜像推送，无镜像发布权限；因此本方案无注册表签名权限变更，固定SHA512/输入散列/归属检查仍执行。缓存不存env/PFX/数据库/凭证/私有runtime，不把PR缓存内容当可信发布来源。Action固定完整SHA并保持官方LICENSE/版本登记；有限依赖审查不是完整供应链认证。

## 替代方案与选择

1. BuildKit gha：Docker官方说明docker driver须启containerd image store；GitHub runner不可假定支持。零依赖本仓库JS Action可以继承运行时认证，但不能解决驱动兼容。为解决而改全局daemon或另拉未批准BuildKit镜像均扩大变更。
2. GHCR不可变镜像：需要packages写权限、镜像发布/署名/保留规则和配额审批，当前不推荐。
3. 自写内部cache v2 Twirp/Azure blob协议：没有新包但维护/安全面大，非公开REST稳定接口，不推荐。
4. 本申请：复用官方cache restore/save与现有docker save/load，最小权限、无新容器镜像依赖；冷构建/导出和还原耗时实测记录。

来源（已查询）：https://github.com/actions/cache/tree/55cc8345863c7cc4c66a329aec7e433d2d1c52a9 、https://docs.docker.com/build/cache/backends/gha/ 、https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manage-caches 。实际仓库缓存占用/配额必须在启用前只读确认；不假定用户账单或费用。

## 请求的人类决策

批准上述两个官方Action精确SHA、仅现有免费/已含配额范围内缓存、不新增发布/付费权限；或者暂不批准，则E0-A真实跨run验证BLOCKED，继续无关M3源码工作，最终不能宣称全部完成。
