# ADR-007 · main保护规则建议

状态：PROPOSED，仅建议不实施仓库规则修改。2026-10-25 Wave2要求重新只读查询GitHub分支/规则事实，具体观察归档在本轮证据。建议为main要求同Head工程/安全/前端CI、至少一位非实现者PR审查、禁止强推/非快进和删除，紧急旁路需人类审计。当前无修改仓库规则授权，Master不调用写API；启用前继续依靠独立Reviewer、真实分支CI、Master唯一集成与普通push。GitHub计费/配额未知时不启新收费Runner。

OBSERVED：2026-10-25 gh api repos/on-dotnet/ontology-platform/branches/main返回protected=false，SHA=e930935749bcb88d51abb94db4a41695bbbe6717。只读rulesets API返回HTTP403（当前私有仓库套餐不提供该功能，提示升级或公开）；不升级、不公开、不修改规则。保护状态实际可见，规则详情NOT_VERIFIED；继续任务分支CI+独立审查+Master唯一集成。

## G1-CLOSE-001只读复核与单人仓库方案

2026-10-25当前main仍protected=false，Base=d181f66；rulesets仍HTTP403提示需升级或公开。原始只读响应见本轮master/main-protection.json和rulesets.json；未执行任何设置写API。

建议待人类配置授权且套餐支持后：require PR、固定同Head checks engineering/governance-integration、分支需最新基线、解决讨论、禁force/delete。独立Agent报告应随PR留证，Agent同账号并非另一位GitHub审批人。单人仓库先允许PR但required approvals=0，仍人工/独立Agent审查；有另一位获授权且有write权限的真实协作者后再启用1批准/过期批准撤销。避免启用无法满足的自批门槛而迫使常态admin绕过。

官方保护规则允许要求CI和PR；私有库保护依赖Pro/Team/Enterprise等可用套餐，当前API已实际拒绝。套餐/组织权限和具体费用未知，不升级、不公开仓库；PR和重复CI会消耗现有Actions分钟，是否额外计费取决配额，不能承诺零成本。写保护需要仓库管理或edit repository rules权限，紧急旁路需单独人类审计。启用前仍沿用本轮任务分支真实CI+独立Review+Master普通push。

官方来源（本轮读取）：[保护规则/可用套餐/权限](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)、[PR与批准数量可分开要求](https://github.blog/changelog/2021-11-09-require-pull-requests-without-requiring-reviews/)、[PR reviews](https://docs.github.com/en/pull-requests/reference/pull-request-reviews)。上述是建议，尚未实施。
