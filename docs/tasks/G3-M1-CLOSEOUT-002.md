# G3-M1-CLOSEOUT-002 实施计划与路径合同

状态：IN_PROGRESS。授权为人类2026-10-27正式批准附件V1全部任务，原文见../evidence/G3-M1-CLOSEOUT-002/authorization-v1.md。Base=47935fb2eda3d708e628a1b23ccd897e2250ff33，开工fetch确认origin/main相同。

Goal：永久修复正式Review V3、Fuseki单一构建来源与资源生命周期，真实Mac Docker清理并提交同HeadCI和唯一ZIP复审。不重做M1业务、不进M2、不改历史、不跨项目清理。

架构：保留V1/V2读取兼容，在现有正式构包器增加V3选择/聚合/实查CI；Fuseki改为内容寻址固定镜像复用；清理复用精确白名单执行器和持久history诊断。无新直接依赖。

Master唯一拥有公共合同、AGENTS/PLANS/CI、当前授权、任务和master证据；Master独立托管树g3-m1-closeout-master，分支codex/g3-m1-closeout-master。独立worker用各自托管树与codex分支，不覆盖他人改动。Reviewer非作者只读。

- [ ] H1：真实Git/工具链/Docker before。保护原树6个未跟踪.DS_Store；不读取env/卷内容。
- [ ] H2，PACKAGE owner：scripts/create-review-package.ps1、scripts/tests/ReviewPackage.Tests.ps1、docs/development/review-package-spec.md及本任务PACKAGE证据。其它只读。先负例再实现；V1/V2兼容、53PNG/55256ignored、索引/CI/散列/体积门禁。
- [ ] H3，RESOURCE owner：backend/src/AppHost/G2Infrastructure.cs、Fuseki构建入口/相关AppHost启动脚本、scripts/acceptance/g2-integration.ps1、scripts/maintenance/**、对应资源/构建回归测试、本任务RESOURCE证据。公共CI/verify由Master接入。先负例再实现；精确范围/过期/指纹拒绝。不得自行删除真实资源，Master统一盘点审批Apply。
- [ ] Master：H4 EOF与H5永久效率/生命周期规则、自动回归接入；Docker清单逐项归属、准确白名单、独立审查后真实Apply、before/after和开发环境保留验证。
- [ ] 独立任务审查与全分支审查，修复后提交/push；同Head engineering/governance-integration实际成功，再main集成push及唯一V3构包/独立重开。

验收：pwsh -NoProfile -File scripts/verify.ps1 -SelfTest；适用脚本/真实Docker fixture与增量后端构建/语义集成；git diff --check；最终同HeadCI。缺前提明确BLOCKED/NOT_RUN；物理回收无证据NOT_VERIFIED。安全清理不以统一DEFERRED替代。

冻结顺序：测试 → 独立Review → 提交 → 同HeadCI → 构包 → 独立重开 → 交付。只输出一个包及G3_M1_CLOSEOUT_READY_FOR_REVIEW后停等ChatGPT复审。
