# G3-M1-CLOSEOUT-002 实施计划与路径合同

状态：READY_FOR_REVIEW / PARTIAL（最终同HeadCI/唯一ZIP由提交后实际回执确认）。授权为人类2026-10-27正式批准附件V1全部任务，原文见../evidence/G3-M1-CLOSEOUT-002/authorization-v1.md。Base=47935fb2eda3d708e628a1b23ccd897e2250ff33，开工fetch确认origin/main相同。

Goal：永久修复正式Review V3、Fuseki单一构建来源与资源生命周期，真实Mac Docker清理并提交同HeadCI和唯一ZIP复审。不重做M1业务、不进M2、不改历史、不跨项目清理。

架构：保留V1/V2读取兼容，在现有正式构包器增加V3选择/聚合/实查CI；Fuseki改为内容寻址固定镜像复用；清理复用精确白名单执行器和持久history诊断。无新直接依赖。

Master唯一拥有公共合同、AGENTS/PLANS/CI、当前授权、任务和master证据；Master独立托管树g3-m1-closeout-master，分支codex/g3-m1-closeout-master。独立worker用各自托管树与codex分支，不覆盖他人改动。Reviewer非作者只读。

- [x] H1：真实Git/工具链/Docker before。保护原树6个未跟踪.DS_Store；不读取env/卷内容。
- [x] H2，PACKAGE owner：scripts/create-review-package.ps1、scripts/tests/ReviewPackage.Tests.ps1、docs/development/review-package-spec.md及本任务PACKAGE证据。其它只读。先负例再实现；V1/V2兼容、53PNG/55256ignored、索引/CI/散列/体积门禁。
- [x] H3，RESOURCE owner：backend/src/AppHost/G2Infrastructure.cs、Fuseki构建入口/相关AppHost启动脚本、scripts/acceptance/g2-integration.ps1、scripts/maintenance/**、对应资源/构建回归测试、本任务RESOURCE证据。公共CI/verify由Master接入。先负例再实现；精确范围/过期/指纹拒绝。不得自行删除真实资源，Master统一盘点审批Apply。
- [x] Master：H4 EOF与H5永久效率/生命周期规则、自动回归接入；Docker清单逐项归属、准确白名单、独立审查后真实Apply、before/after和开发环境保留验证。
- [x] 独立任务审查与全分支审查及自然代际证据限定复核，均PASS。
- [ ] 提交后门禁：最终同Head engineering/governance-integration实际成功，再main集成push及唯一V3构包/独立重开；以实际交付回执确认，不预填自身未来CI。

验收：pwsh -NoProfile -File scripts/verify.ps1 -SelfTest；适用脚本/真实Docker fixture与增量后端构建/语义集成；git diff --check；最终同HeadCI。缺前提明确BLOCKED/NOT_RUN；物理回收无证据NOT_VERIFIED。安全清理不以统一DEFERRED替代。

冻结顺序：测试 → 独立Review → 提交 → 同HeadCI → 构包 → 独立重开 → 交付。只输出一个包及G3_M1_CLOSEOUT_READY_FOR_REVIEW后停等ChatGPT复审。


## 实际路径/审查与修复轮

PACKAGE Owner=package，独立托管树/Users/chasen/.codex/worktrees/g3-m1-closeout-package/ontology-platform，分支codex/g3-m1-closeout-package，原源码0a873be/证据77b8ff0；Reviewer=inventory_review。初次ignored聚合P2修复后限定复审通过；90/0+真实PNG大夹具1/0，最终体积2482853/32803202 bytes。

RESOURCE Owner=resources，独立树/Users/chasen/.codex/worktrees/g3-m1-closeout-resources/ontology-platform，分支codex/g3-m1-closeout-resources，原35c2da0/f2d8e7f，Reviewer=resource_review。必要AppHost路径授权补充DevelopmentInfrastructure.cs/CanonicalFusekiImage.cs，P2唯一修复轮补充Program.cs/ResourceLifecycle.cs、wave2-runtime.py、ResourceLifecycle.Tests.py，先冻结所有权后实施，Master未并写这些路径。新归属8回归和既有边界/Release通过，限定复审PASS。

Master实际35项Docker Apply成功、保留8卷四服务前后健康通过；原代际变更拒绝保留，generation2精确计划重新独立审查。全量矩阵与日志见本任务master/delivery-report.md。最终整合SelfTest/独立Review/同HeadCI/唯一包另以真实回执收口。


最终CI唯一修复波：fdafb的run40487172435 attempt1在镜像获取600秒超时（非业务测试失败），保留日志与未知内部阶段。RESOURCE相同owned_paths补canonical失败脱敏receipt/CI摘要及10项回归，原a3d263b+f319717，Master ba578fc+c8b75ff，whole_review两段限定复审PASS。Master增量10/2real/static通过；不改Dockerfile/600预算/依赖/业务。新最终Head CI与唯一包必须实际后置读取，不复用旧Head结果。
