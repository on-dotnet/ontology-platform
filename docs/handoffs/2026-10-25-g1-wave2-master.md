# G1 Wave2 Master 交接

当前关口G1-WAVE2，Mac本机功能验收PASS、总交付PARTIAL，停止等待外部复审，不进G2。完整[报告](../evidence/G1-WAVE2/master/delivery-report.md)、[操作手册](../development/wave2-local-development.md)、[当前授权](../tasks/current-authorization.md)与ZIP manifest共同定义最终事实。

Base=e930935749bcb88d51abb94db4a41695bbbe6717。Master树g1-wave2-master/codex/G1-WAVE2-master，SEC树g1-wave2-sec/codex/G1-SEC-001（cecf43b）、FE树g1-wave2-fe/codex/G1-FE-001（ce28552）、OBS树g1-wave2-obs/codex/G1-OBS-001（a52dc13）。树在用户.codex/worktrees下独立，不复用M0。保持以供复审恢复；不清理含私有运行资产的Master树，不全局prune。最终main只由Master集成，精确最终Head/Push/CI与ZIP见manifest/交付回执。

新开发卷前缀wave2-a5431c01414a，7容器/6命名卷；验收后唯一AppHost受控停止、卷保留。私有runtime/PFX/keyring和随机测试身份只在忽略.tools/security对应目录（权限受限），不进入Git/ZIP。跨设备请按手册重新prepare/core/bootstrap/full，不能复制历史凭证冒充新环境。Node24.22.1/pnpm11.28.8隔离；无全局PATH/SDK/EF/系统信任变更。

已验收：真实5身份310协议、14项完整PG/KC安全套件、4基础宿主、6Web单测/5UI夹具/2真实OIDC、OpenAPI语义、代理/503错误同Trace LGTM、双实例指标、中文Grafana、告警恢复、容器/进程会话持久化。最终独立复审/同HeadCI以报告与manifest为准。ASPIRE010保留；Windows/Intel、镜像完整CVE/SBOM/签名及生产轮换/合规仍有明确边界。
