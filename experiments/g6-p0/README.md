# G6-P0-PARSER-PREP-001

本目录是独立标准库PREP实验，不进入产品运行时。人类授权、完整附件及任务卡位于docs/evidence/G6-P0-PARSER-PREP-001/input和docs/tasks/G6-P0-PARSER-PREP-001.md。附件原始Markdown按source.json保存utf8Text及hash，可无损恢复；不是自动执行文档内所有后续阶段。

## 验收入口

在仓库根运行，Python只用标准库，无pip：

```sh
python3 -B experiments/g6-p0/harness/preflight.py
python3 -B -m unittest discover -s experiments/g6-p0/tests -p 'test_*.py' -v
python3 -B -m unittest discover -s experiments/g6-p0/harness -p 'test_*.py' -v
python3 -B experiments/g6-p0/fixtures/synthetic_seed/verify_seed.py
python3 -B experiments/g6-p0/supply-chain/audit_metadata.py
pwsh -NoProfile -File scripts/verify.ps1 -SelfTest
```

preflight校验原MANIFEST的固定SHA及24输入成员、允许路径、测试发现和import失败。既有execution_preflight不支持G6，不能冒用M5；本入口只适用PREP，无生产DI/audit consumer变化。

## 交付导航

- contracts/parser-contract.md与parser/README.md：版本/Artifact/Map canonical哈希、字节与Unicode、CSV、精确/降级Anchor及安全文件读取；实际API在parser/core.py。
- tests/test_parser.py：35真实用例及9seed/18span；fixtures/edge-cases.json保存异常字节。不会产生图，DOCUMENT_ONLY约束有效。
- contracts/platform-contract.md及harness：六Provider、策略/费用、假secret不泄漏、资源DryRun与Compose静态设计；37测试（含元数据和前置门禁）。
- supply-chain/preparation-report.md：162包/334声明/3493发布制品元数据、4模型仓库候选、精确pin冲突、许可与跨平台未决项。可安装闭包BLOCKED，禁止直接安装观察版本。
- design：跨平台Compose设计、Provider/安全输入、ADR01–09、Gold计划和下一授权草案。compose-plan.json不可直接运行，runnable=false、无映像digest。
- docs/evidence/G6-P0-PARSER-PREP-001：非作者审查、失败修复、实际测试/命令/资源/提交绑定；最终唯一V3在ignored artifacts/reviews。

真实Docling/PaddleOCR/OCR、Docker、API、系统Secret、Windows/Linux测试均NOT_RUN；此处PASS只用于已运行stdlib及工程门禁。任务不合main，等待ChatGPT复审后另行授权。
