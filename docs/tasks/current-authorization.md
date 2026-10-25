# M0 当前授权增量（2026-10-25）

当前关口：**M0-MAC-PORTABILITY-001，READY_FOR_REVIEW / PARTIAL**。Mac最低工程验收、独立审查已通过；Windows等未运行项保留，最终同Head CI/ZIP以manifest为准。仅允许本任务收尾/复审，不启动下一关口。人类在本会话正式批准 Mac Codex Master 接管与跨平台兼容验收，明确读取迁移合同第二节至文末并直接执行。允许项目隔离依赖恢复、开发容器与测试、多 Agent 独立 Worktree/任务分支、独立审查后 Master 集成 main、一个标准 Review ZIP。任务合同与验收矩阵见 [M0 任务卡](M0-MAC-PORTABILITY-001.md)。只批准 M0，不启动 G1 Wave 2 SEC/FE/OBS 或 G2；系统级改动、管理员权限、付费和不明凭证停止对应操作。下文为原 G1 历史索引，原状态不改写。

---

# 当前授权索引

当前：**G1-INFRA-001 V2，READY_FOR_REVIEW**。本机工程验收PASS；仅允许本任务收尾核验/范围内修复与最终ZIP交付，不自动启动其他任务。最终快照/CI见[总交付记录](../evidence/G1-INFRA-001/delivery-report.md)及包内manifest。2026-10-23用户明确选择“按V2全部授权执行，采用Worktree并行”。依据为已完整读取的`OntologyPlatform-CodexMaster-G1-INFRA-001-Parallel-Worktrees-ReviewPack-V2.md`，归档在本阶段证据目录。

覆盖旧的单checkout/默认直接main偏好，不追溯改写先前用户消息或G0/G1-ENG证据。允许项目隔离稳定工具链准备、Git并行协作纠偏、标准审查ZIP、AppHost/ServiceDefaults/最小健康API及开发PG/Jena/RustFS/Keycloak资源。

不授权G1-SEC/G1-FE/G1-OBS/G2或正式业务。管理员安装、机器PATH/默认工具修改、系统Docker安装/WSL修改、不明凭证和付费操作停止报告。

任务卡：[G1-INFRA-001](G1-INFRA-001.md)。历史[G1-ENG-001](G1-ENG-001.md)仍为已交付待审PARTIAL。Master负责main集成，独立写任务使用独立Worktree和分支，公共配置单写者。
