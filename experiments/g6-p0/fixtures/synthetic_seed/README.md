# G6-P0 合成验证种子（不是黄金集）

这 9 个纯合成 Markdown/TXT/CSV 文件只帮助设计 PoC 反例和 SourceAnchor 数据格式。**它们不代表真实 Docling、OCR、LangExtract、Jena、pgvector 或 Agent 已通过任何运行验证。**

文件覆盖：跨厂同炉号、测点冲突、否定和假设、Prompt Injection、DOCUMENT_ONLY、修订证据、CSV 行列头/单位、撤销文件权限。

- `seed-manifest.json` 只给出片段原文、Unicode codepoint 精确起止和待验证的语义判据；这不是经过双人业务专家审定的 Gold。
- `verify_seed.py` 只用 Python 标准库验证种子 SHA256 和代码点范围是否自洽；不安装或调用任何第三方项目。
- 真正的 G6-P0 Gold 需要 D4 全部格式、扫描 PDF、OCR、Office、多工作表等 **30 份+5 负例**，以及至少两位业务专家独立标注/仲裁。
- 在用户明确批准使用文档和模型前，禁止拿真实生产材料替换此包并发送至外部服务。

本包故意**不生成 PDF/DOCX/XLSX/PPTX 伪样本**：这些格式需要规范工具和真实可验证结构，不能仅凭扩展名当作解析质量实验。
