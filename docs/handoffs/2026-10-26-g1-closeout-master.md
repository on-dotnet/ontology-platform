# G1-CLOSE-001 Master交接

当前关口G1-CLOSE-001，Mac本轮修复/纵向验收PASS，总体G1 PARTIAL，完整报告及精确Head/CI以本轮交付与唯一ZIP manifest为准。Base=d181f66e569e190a66b0f48b179f2fd9390b9467。交付后停止，不进G2。

- Master：/Users/chasen/.codex/worktrees/g1-close-master/ontology-platform；codex/G1-CLOSE-001-master。公共合同/迁移/CI/脚本/主线唯一集成人。
- SEC：/Users/chasen/.codex/worktrees/g1-close-sec/ontology-platform；codex/G1-CLOSE-SEC，5d92109064980e61fb7ac5a74cc98624c7219f0c，已push/专项review0/0/0。
- OBS：/Users/chasen/.codex/worktrees/g1-close-obs/ontology-platform；codex/G1-CLOSE-OBS，19355e0919d5f4368b1218524af075da57e9dd1d，已push/专项及两次限定review0未解决。
- 保留全部M0/Wave2树，不清理/重写；原main六个.DS_Store未跟踪用户现场不删除，不作为交付源码。新三树保留供外部复审/恢复。

本轮新开发卷前缀wave2-a19529d4edb4，7容器/6命名卷。全部验收后正常停止AppHost，卷保留；私有runtime/PFX/keyring/Realm仅本Master忽略.tools/security对应目录，不输出、不打包、不复制历史认证。新机器按手册prepare/core/bootstrap/full重新生成。恢复本机可用同一private runtime按full启动，禁止将开发HTTP/回环源当生产HA。

验收脚本通过进程PLATFORM_EVIDENCE_DIR=docs/evidence/G1-CLOSE-001/master写本轮目录；浏览器截图用PLATFORM_SCREENSHOT_DIR=../../docs/evidence/G1-CLOSE-001/master/ui。默认历史路径只供原阶段复现，新阶段必须显式选新目录。verify-dependency-fault/persistence恢复必须等双API，各自Npgsql池首次503是过渡，不能仅第一实例200后把流量全面恢复。API进程替换脚本仅内存持Cookie，Master受控停止/重启唯一本树AppHost后按Enter；不保存Cookie。

[交付报告](../evidence/G1-CLOSE-001/master/delivery-report.md)、[退出矩阵](../planning/g1-closeout-acceptance.md)、[只读G2准备](../planning/g2-readiness-readonly.md)。Windows/Intel/供应链/生产目标/Faro/通用Outbox等保留未运行/未知，不能从45项测试或配置推断产品业务已完成。
