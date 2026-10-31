# ADR状态、Gold计划与下一阶段授权申请

本任务完成标准库PREP，不代表G6产品、OCR或模型PoC完成。附件PRD是设计输入，不授权其P01–P12页面、发布、迁移或生产数据。原G2/G3正式合同和资源一字未改。

| ADR | 当前决策/证据 | 未决验证与回退 |
| --- | --- | --- |
| G6-01解析与部署 | DEFER运行时选型；自有Document IR/Version/Artifact/Anchor/Map标准库已实现；优先Docling、PaddleOCR补充 | 同输入真实PDF/扫描/DOCX/PPTX/XLSX质量、RSS、时间、平台；失败保留UNKNOWN/BLOCK，不伪造坐标；替代需新批准 |
| G6-02抽取与模型 | DEFER模型/embedding/维度；六Provider配置及成本负例已验 | 真实schema/工具/视觉/外联、模型方差与Gold；失败不得写正式图 |
| G6-03知识图部署 | DEFER独立dataset或进程裁决；保持canonical Jena | 独立资源图/索引切换、回滚、ACL故障注入；G3图只读 |
| G6-04审核发布 | DEFER业务低风险批审/异人审核 | 版本、审批hash、撤权、半发布失败；没有审批不激活 |
| G6-05检索 | DEFER索引/过滤/融合 | 当前权限复核、跨scope负例、精确gold与置信区间；失败不降级泄露 |
| G6-06任务运行时 | DEFER既有Run复用或KnowledgeJob | lease/重启/取消/SSE/幂等实测；保持现有协议 |
| G6-07资源生命周期 | ACCEPTED_DESIGN；离线同Task/Run/版本/TTL/KEEP拒绝已验 | Compose/删除执行器未实现；实际Docker资源创建0，全部旧资源KEEP |
| G6-08Gateway/Secret | ACCEPTED_DESIGN；配置、精确费用、固定错误、假secret不泄漏已验 | 真实OS store/TTY/容器秘密/分布式账本与Provider均NOT_RUN |
| G6-09商用许可 | ACCEPTED_POLICY；精确PyPI元数据及风险清单 | wheel内NOTICE、原生库、weights/model card、分发/SaaS义务未审，安装闭包BLOCKED |

MinerU不进入默认依赖或镜像；附件所述特殊许可需业务/法律独立确认，不因公开可下载视为许可批准。没有必要复制其代码/权重，本轮未访问或安装。

## Gold Set与实验公平性

当前9 seed/18span和随机/边界测试仅合成开发夹具，不是业务专家Gold。下一阶段申请30代表性文件+5安全/损坏负例，至少两位业务专家标注并裁决，记录版本、分歧、原因、许可与脱敏；至少300候选，含40否定/条件/假设/跨厂重号/冲突/时间/单位难例。测试集不得进入prompt范例，按文件/来源分组隔离防泄漏。

固定inputSha、parser及权重digest、IR版本、model/registry、recipe/schema、ontology release、gold版本和随机seed。对非确定模型重复并报告区间。报告Entity/Relation的TP/FP/FN和precision/recall/F1；Anchor P@1和exact coverage分开；Schema有效数/全部响应（拒绝截断单列）；跨厂误合并数/全部自动合并建议，分母0记N/A；每文件时延、峰值RSS和USD。候选F1等阈值只是实验筛选，样本不足INCONCLUSIVE；越权0、无人审不激活、原文hash和G3不可变为硬门禁。

## 下一授权草案（当前不可执行）

1. 先批准只做完整平台依赖求解与许可复核：冻结Python精确patch/目标平台；选择Docling完整standard或最小slim路线；对所有selected extras和markers求解，输出每平台精确wheel文件/hash/size及原生NOTICE。当前观察版本不作为requirements，发现固定约束冲突先修候选，不安装碰运气。
2. 当闭包无UNKNOWN且经非作者审查后，单独申请隔离安装/模型权重/镜像。候选root docling/docling-slim 2.145.0、paddleocr/paddlex 3.7.0、paddlepaddle 3.2.2；不承诺它们可共存，详见供应链报告。拟Python3.12系列但patch未冻结，故本草案不具有执行条件。每平台一次性venv/容器，CPU先行，未知容量不保存；禁止改系统PATH/默认SDK/现有G3资源。
3. 网络白名单逐URL限定pypi.org元数据、files.pythonhosted.org已批准wheel、精确模型仓库revision的对象URL、批准镜像registry；不允许一般联网和运行期自动download。预算按已列artifact size求和并预留磁盘，unknown size阻断。初始资源建议单worker≤4CPU/8GiB内存/20GiB磁盘/60min，容量实测不满足则BLOCKED，不能改宿主设置。
4. 解析PoC只用有许可的合成/脱敏文件；原生PDF与OCR分组，Office公式同时保留公式与缓存值并禁止执行/外链；大文件/zip bomb/损坏/宏/异常编码/路径穿越/撤权必测。真实每平台构建、健康和exact cleanup需独立授权，不能借PREP开容器。
5. 模型PoC另单：确定Provider、region、模型版本、价格快照、数据分类/样本hash、最多50请求与5USD的更严格双限、单并发/有限重试。用户确认后才真实TTY无回显输入。以上数字仅建议；任何未知价格/预算/出口拒绝执行。

下一阶段的安装、镜像、weights、真实key/API、G6-01以及main集成都未获本轮授权。收到独立复审后再由人类发出新任务，不自动启动。
