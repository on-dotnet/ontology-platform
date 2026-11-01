# 本轮测试矩阵

| 项目 | 实际状态 | 证据/限制 |
| --- | --- | --- |
| ZIP CRC/Manifest/SHA256SUMS | PASS | 15成员、13 Manifest payload、14 SHA256SUMS；input-integrity.json；Reviewer独立核验 |
| 现有工具能力 | BLOCKED_WITH_WITNESS | pip26.2.2 dry-run可fallback wheel；工具/帮助真实读取，求解NOT_RUN |
| Docling PDF/Office/Markdown extras | METADATA_OBSERVED | 新根独立传播，各54节点/79边；不等于解析质量 |
| T1 aarch64 / T2 x86_64 | METADATA_OBSERVED | 各57条件候选，patch/glibc/digest未知；runtime NOT_RUN |
| 快照约束 | BLOCKED_WITH_WITNESS | docling-core→doclang<0.9，观察0.9.0；唯一替代0.8.0仅该单边满足，不称全局UNSAT或完整可解 |
| 初版定向测试 | 19 PASS但覆盖不足 | Reviewer实际P1架构负例失败，原源码/错误候选完整保留 |
| 修复后定向正反测试 | 24 PASS / exit0 | targeted-tests-committed.source.json，独立Reviewer也24/exit0；URL/JSON/平台/ABI/patch/extras/重复/pin/yanked/漂移/伪READY拒绝 |
| 初始静态与SelfTest入口 | FAIL / exit1 | YAML解析库发现缺口；均在structured-syntax短停，未进入完整套件；未隐去 |
| 工具复用后静态 | PASS / exit0 | static-final.source.json；修复后最终源码已扫描 |
| 完整SelfTest | PASS / exit0，381.7秒 | selftest-after-tool-reuse.source.json；ReviewPackage103/0failure；未复跑无关产品整栈 |
| PREP parser35+harness37 | REUSED_NOT_RERUN | 原测试commit与当前PREP29个mode/blob/path相同；不混计本轮24项 |
| 许可/NOTICE/安全扫描 | NOT_VERIFIED / NOT_RUN | 三项license字段未知；全部artifact未下载，native NOTICE/SBOM未验证 |
| Docker资源metadata | OBSERVED / exit0 | backend与精确ID集合相等；0容器/8卷/13唯一镜像/5history/3network；不证明服务健康 |
| 真实Docling/OCR/模型/Docker/API/目标Linux运行 | NOT_RUN | 本轮未授权；不读取真实Key、不访问生产 |
| Actions CI | NOT_RUN | 仅任务分支push；workflow_dispatch未触发 |
| diff-check / schema / V3 / 非作者重开 | 见各实际回执 | 构包exit0只认证包完整性，不把整体PARTIAL/BLOCKED升级产品PASS |

Shell诊断一次遍历pip许可证目录遇到IsADirectoryError/exit1，改为精确LICENSE.txt读取后hash核验；仅工具诊断，不属于产品测试。资源盘点130.7秒主要为既有只读分类，After仅运行定向Docker快照约1.9秒，未重复完整盘点。
