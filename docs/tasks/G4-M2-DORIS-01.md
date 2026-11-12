# G4-M2-DORIS-01｜P0 一页状态

唯一状态：**G4_M2_DORIS_P0_BLOCKED_WITH_WITNESS**（2026-11-12）。核对与申请已形成；关键制品元数据和运行资源尚未闭合，不代表产品失败或获准实施。

| 项目 | 当前事实 |
|---|---|
| 授权 | 本会话明确批准附件 P0；后续补充单机测试，以及方案、Docker Compose 必须进入源码供测试/生产使用。后者纳入待批实施范围，不解锁本轮代码、下载和运行 |
| Base | `11595ecb6560f7ed6ceca54666d32b7afcae7f35`；本轮 fetch 后 origin/main 相同 |
| 分支 / Worktree | `codex/g4-m2-doris-01`；`/Users/chasen/.codex/worktrees/g4-m2-doris-01/ontology-platform`，原生托管创建，无安装/setup |
| Owner / Reviewer | Master 唯一文档作者；`/root/p0_reviewer` 非作者只读；无产品 Writer |
| RunId / 资源 | `p0-20261112-01`；仅本树/分支，KEEP 至本任务后续实施及审查完成；不清理历史资源 |
| 已核对 | Doris 4.0.8 FE/BE 官方 ARM64 标签身份；MySqlConnector 2.6.2 nuspec；现行 DTO/凭据/DI/UI/执行器；宿主32GiB、12核、磁盘可用283GiB、Docker可见7.75GiB |
| 关键缺项 | Registry manifest/config 读取保存被自动审批拒绝；逐层大小/命中、完整供应链组成及转向域名未验。Logging 8.0.2 元数据页面两次超时，停止重复。官方 FE8GB+BE16GB 开发建议超过现有VM，缩减合成预算须明确接受并实测 |
| 产品边界 | 单机1FE+1BE、单副本、固定FE/internal catalog/单database，仅元数据。FE/BE是同机必要组件，不是多节点要求。Compose及测试/生产配置源码化，但无生产系统访问、部署或写入 |
| 验证 | 文档格式/相对链接/diff-check exit0；非作者Review PASS（仅P0文档）；产品测试、完整SelfTest、prepare、CI、Windows/Intel、TLS/权限/取消真实服务全部 NOT_RUN |
| 本轮非目标 | 不下载依赖/镜像层、不安装、不启动、不生成证书、不改产品/锁/共享脚本、不制作ZIP、不更新main |

**owned_paths（仅P0）**：`docs/tasks/G4-M2-DORIS-01.md`、`docs/evidence/G4-M2-DORIS-01/admission-request.md`、`docs/tasks/current-authorization.md`（仅追加）。其它路径均 read_only_dependencies，重点为 Contracts/G4、Connections、Api/G4、Web connections、workflow 系列、verification-gates、现行工程政策。公共合同与锁后续仍由 Master 单写。

**下一动作**：审阅[一次性准入申请](../evidence/G4-M2-DORIS-01/admission-request.md)中的 A–F 决策及硬停止条件；批准后在本会话、本树、本分支继续。先补齐被拒元数据与精确闭包，再准备/实施，不另建工程优化或恢复任务；未获批停止于 P0。
