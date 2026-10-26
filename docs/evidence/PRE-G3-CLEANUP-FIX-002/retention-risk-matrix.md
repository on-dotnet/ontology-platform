# 保留与后续一次性处理矩阵

每项具体事实独立于旧聊天可见性。无开放PR且阶段关闭已核实；仅下列边界保留，不阻碍安全白名单Apply。

## Git 非祖先原始refs

|ref|tip|cherry + / -|处理与解除条件|
|---|---|---:|---|
|codex/G1-SEC-001|cecf43b00f4f5f12c9309640d68ed665f2643498|0 / 5|全部补丁有main等价映射，但原tip非祖先；正常branch -d/本轮祖先删除合同不允许强删。保留低成本恢复refs；干净且无私有内容的旧工作目录可单独移除。后续如获明确非祖先ref删除例外，再按逐提交映射核验。|
|codex/G2-AI-001|741cde0b206ada85fcc7769e6e12bdc474ab70df|0 / 17|全部补丁有main等价映射，但原tip非祖先；正常branch -d/本轮祖先删除合同不允许强删。保留低成本恢复refs；干净且无私有内容的旧工作目录可单独移除。后续如获明确非祖先ref删除例外，再按逐提交映射核验。|
|codex/G2-FE-001|068878b9312c9d39430945677f0835fb2e48fae0|0 / 11|全部补丁有main等价映射，但原tip非祖先；正常branch -d/本轮祖先删除合同不允许强删。保留低成本恢复refs；干净且无私有内容的旧工作目录可单独移除。后续如获明确非祖先ref删除例外，再按逐提交映射核验。|
|codex/G2-FINAL-FIX|9689a5e8099144b060131ee4d1a185f5b5285859|0 / 1|全部补丁有main等价映射，但原tip非祖先；正常branch -d/本轮祖先删除合同不允许强删。保留低成本恢复refs；干净且无私有内容的旧工作目录可单独移除。后续如获明确非祖先ref删除例外，再按逐提交映射核验。|
|codex/G2-HOST-FIX|44f45bb7ef9d5f5c840bdcb4e5073ebbb8f2e152|0 / 3|全部补丁有main等价映射，但原tip非祖先；正常branch -d/本轮祖先删除合同不允许强删。保留低成本恢复refs；干净且无私有内容的旧工作目录可单独移除。后续如获明确非祖先ref删除例外，再按逐提交映射核验。|
|codex/G2-OBS-SUPPORT|75ae3742879e50453313bf2e685c5c3c8c2b91a2|0 / 4|全部补丁有main等价映射，但原tip非祖先；正常branch -d/本轮祖先删除合同不允许强删。保留低成本恢复refs；干净且无私有内容的旧工作目录可单独移除。后续如获明确非祖先ref删除例外，再按逐提交映射核验。|
|codex/G2-PUB-001|83d25cca70b41cea8de19bdac79d805a76957a21|0 / 10|全部补丁有main等价映射，但原tip非祖先；正常branch -d/本轮祖先删除合同不允许强删。保留低成本恢复refs；干净且无私有内容的旧工作目录可单独移除。后续如获明确非祖先ref删除例外，再按逐提交映射核验。|
|codex/G2-QA-FIX|e4b5bdee6508b747cda17136534c03e023c3d99f|0 / 4|全部补丁有main等价映射，但原tip非祖先；正常branch -d/本轮祖先删除合同不允许强删。保留低成本恢复refs；干净且无私有内容的旧工作目录可单独移除。后续如获明确非祖先ref删除例外，再按逐提交映射核验。|
|codex/G2-QRY-001|3fc61d6a73290a8576c421ae0b0bdae7486f0030|2 / 10|真实非等价补丁，具体patch-id/路径差异见git-before-classification.json；未来限域核对当前实现及独立Review后决定补集成或放弃，当前不改G2业务。|
|codex/G2-READINESS-TEST|a02d6da7297b254ce153628f29cf765de10af77c|0 / 1|全部补丁有main等价映射，但原tip非祖先；正常branch -d/本轮祖先删除合同不允许强删。保留低成本恢复refs；干净且无私有内容的旧工作目录可单独移除。后续如获明确非祖先ref删除例外，再按逐提交映射核验。|
|codex/G2-SEC-SUPPORT|219d1fcad3046251a1419f985dacab703f31c4cb|1 / 9|真实非等价补丁，具体patch-id/路径差异见git-before-classification.json；未来限域核对当前实现及独立Review后决定补集成或放弃，当前不改G2业务。|
|codex/G2-SEM-001|b16c62808a7bf0b659d587d0f5c8fcd08a4cca5b|1 / 22|真实非等价补丁，具体patch-id/路径差异见git-before-classification.json；未来限域核对当前实现及独立Review后决定补集成或放弃，当前不改G2业务。|

## Worktree 6项保护

- primary main：唯一main集成；保留六个原有.DS_Store未跟踪文件，Git不覆盖。
- pre-g3-hygiene：当前FIX002 Master任务、审查与恢复。
- g2-master：三套实际私有runtime/realm/PFX，元数据见原Git盘点protectedPrivatePathMetadata。
- g2-query：2个非等价补丁，query-plan/测试/锁依赖差异，保留原始树和refs。
- g2-security：1个非等价guard补丁及最终范围差异，保留。
- g2-sem：1个非等价合同修订，当前不获授权改G2合同，保留。

g2-ai在Master任何Apply前外部消失：不计本轮实际删除，保留初始盘点和对应refs，不伪报回收。

## Docker 逐对象KEEP

选定g2-ef979bd04cc0为可复用的既有G2合成开发环境，已用原可信启动器实际恢复并健康探针。它是明确选定的复用环境，并非宣称原测试卷本来就是固定生产式开发环境。其它两组g2-712190660deb/g2-b59e68191ca0分别有实际私有runtime/realm/PFX绑定，无独立完整备份/替代方案，依附件暂保留；解除条件是独立可恢复备份和明确替代方案，不要求旧聊天不存在证明。

- g2-712190660deb-alloy-data：对应上述准确恢复组，保护。
- g2-712190660deb-fuseki-data：对应上述准确恢复组，保护。
- g2-712190660deb-grafana-data：对应上述准确恢复组，保护。
- g2-712190660deb-loki-data：对应上述准确恢复组，保护。
- g2-712190660deb-postgres-data：对应上述准确恢复组，保护。
- g2-712190660deb-prometheus-data：对应上述准确恢复组，保护。
- g2-712190660deb-rustfs-data：对应上述准确恢复组，保护。
- g2-712190660deb-tempo-data：对应上述准确恢复组，保护。
- g2-b59e68191ca0-alloy-data：对应上述准确恢复组，保护。
- g2-b59e68191ca0-fuseki-data：对应上述准确恢复组，保护。
- g2-b59e68191ca0-grafana-data：对应上述准确恢复组，保护。
- g2-b59e68191ca0-loki-data：对应上述准确恢复组，保护。
- g2-b59e68191ca0-postgres-data：对应上述准确恢复组，保护。
- g2-b59e68191ca0-prometheus-data：对应上述准确恢复组，保护。
- g2-b59e68191ca0-rustfs-data：对应上述准确恢复组，保护。
- g2-b59e68191ca0-tempo-data：对应上述准确恢复组，保护。
- g2-ef979bd04cc0-alloy-data：对应上述准确恢复组，保护。
- g2-ef979bd04cc0-fuseki-data：对应上述准确恢复组，保护。
- g2-ef979bd04cc0-grafana-data：对应上述准确恢复组，保护。
- g2-ef979bd04cc0-loki-data：对应上述准确恢复组，保护。
- g2-ef979bd04cc0-postgres-data：对应上述准确恢复组，保护。
- g2-ef979bd04cc0-prometheus-data：对应上述准确恢复组，保护。
- g2-ef979bd04cc0-rustfs-data：对应上述准确恢复组，保护。
- g2-ef979bd04cc0-tempo-data：对应上述准确恢复组，保护。

固定依赖镜像及最新AppHost/集成镜像完整ID见approved-candidates.json keep，恢复验证新增镜像/容器/history以docker-preapply/after的集合差记录，不混入原白名单。镜像版本/摘要与AppHost固定合同未改。默认bridge/host/none在同一代际的Apply→shutdown区间ID保持相同；自然新代际的bridge变化单列实际ID与时间，不宣称全过程ID不变。

BuildKit原13记录约500.1MB为Docker Desktop共享缓存，du无法证明各记录按本项目独占；不运行任何global prune。Docker build history记录精确删除不等于cache字节释放。后续采用项目隔离builder需另获配置授权；本轮明确保留共享cache。

## 公开history风险

有限模式覆盖及独立人工triage未发现需轮换的真实凭证；6命中都是生成表达式/合成边界fixture。发现真实外泄应立即报告、轮换，并单独审批历史处理；本轮不改Git历史。任意混淆、语义隐私、未获取对象、生产/Windows/Intel验证仍NOT_VERIFIED。

## Review ZIP

现有有效Hygiene ZIP保持到新FIX002 ZIP成功独立重开，之后只按精确旧路径/2,021,459 bytes/SHA256 0e06b72d176018e07464eeb2f934e4167bb740560dd557c22c0af9e427e13ab7删除。旧唯一runtime元数据和完整交付收据已单独归档；原源码/diff/OID可从Git恢复，原ZIP字节不能承诺重现。

实测网络边界：初始docker-before至preApply之间bridge ID从210e5297…变为de218450…，原因NOT_VERIFIED；此变化已发生在Apply之前，未归因为本轮清理，也未修复或重建网络。preApply→afterApply→正常shutdown三个默认网络完整ID严格相同。532条删除日志没有网络命令；恢复进程只创建并正常清除自己的Aspire会话网络。原始ID完整保留在JSON，不把外部漂移静默规范化。

保留本地/远端各15 refs的完整构成：main + 当前FIX002任务枝 + codex/G2-THIN-SLICE-001-master（46c7a6de70b1b97c032b12a19bc27c1c54e70f4c，为main祖先但仍附着私有恢复树）+ 12非祖先原refs。保护G2 Master的这一祖先ref单独保留，不归入12非祖先组。

后验history I1已通过e40修复、40回归/额外独立15+9专项、同HeadCI、仅原18子计划36日志和18强DB无记录诊断整改；随后自然VM新代际48a→212a，原18没有回现。原532即时快照/后验19记录仍保留。唯一资源266，变更命令尝试284，不能把重试再算18回收。未主动restart/update/改设置/网络/内部DB。
