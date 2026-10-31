# Docling / PaddleOCR 供应链准备结果

状态：声明图枚举完成；可安装依赖闭包 **BLOCKED**。未安装第三方依赖、未下载wheel/sdist、未下载模型权重。元数据许可声明不等于法律批准，文件散列为注册表声明而非下载验证。

## 精确根候选及采集方法

Docling/docling-slim 2.145.0（Python>=3.10,<4.0）；PaddleOCR/PaddleX 3.7.0（>=3.8）；PaddlePaddle 3.2.2（CPU研究候选，兼容未实测）。[Docling精确元数据](https://pypi.org/pypi/docling/2.145.0/json)、[PaddleOCR精确元数据](https://pypi.org/pypi/paddleocr/3.7.0/json)。代码许可声明Docling MIT、PaddleOCR/PaddleX Apache-2.0、PaddlePaddle Apache，需继续检查对应发布artifact内许可。[Docling源许可证](https://github.com/docling-project/docling/blob/v2.145.0/LICENSE)、[PaddleOCR源许可证](https://github.com/PaddlePaddle/PaddleOCR/blob/v3.7.0/LICENSE)。

pypi-metadata.json保留每个包的精确观察version、requires_python、所有requires_dist（含未选extra）、所选extra传播、registry URL/时间/raw hash、每个发布文件名/size/SHA256/URL/yanked、声明license/project URL和PyPI已报漏洞。并发最多4，单响应上限4MiB；超限拒绝后改精确release URL，先前失败保留priorMetadataFailures。无payload下载；没有使用pip、依赖求解器或import第三方包。观察transitive最新版并不声称其满足上游范围。

固定点包括docling标准集合、选定Office/Markdown/PDF/convert-core/models-local和paddlex ocr-core，命名transitive extras继续传播；环境marker保留而不执行，形成保守跨平台并集。audit_metadata.py只审声明图节点/extra缺失和简单精确pin不符，明确不是PEP508求解器；负例证明缺节点/extra/强制版本不会被写成安装成功。

当前162节点、334条已选声明，缺失节点0、未传播extra0；元数据抓取失败0。graph-audit.json记录全部简单精确pin不符，不能把图齐全解释为约束闭包。

## 已查明的阻断和路径选择

- `docling==2.145.0`必带`docling-slim[standard]`，会引入torch等；不能将最小slim清单冒充完整docling默认安装。最小路线应显式选slim extras，真实layout/table推理仍需models-local及相应权重。两条路线必须分别求解并比对质量，不能静默删除功能。
- PaddleX强制`opencv-contrib-python==4.10.0.84`、`PyYAML==6.0.2`；PaddlePaddle强制`opt-einsum==3.3.0`。观察到的不同注册表最新版不是可用锁；required-pin-metadata.json另外核验这三个精确版本的发布文件。
- PaddleX要求numpy<2.4，而观察numpy2.5.4不满足，须回溯选择；跨框架torch/torchvision/transformers、CUDA包与Paddle CPU不是同一可移植运行时，GPU extra应排除或单独授权。未进行完整范围/ABI求解。
- Mac原生wheel不等于Linux ARM64容器wheel；Windows宿主使用WSL2 Linux AMD64与原生win_amd64是两种目标。候选Python3.12需精确patch，cp/abi3/glibc和CPU指令实际匹配后才能批准。文件名hint仅索引，不能给平台PASS。
- 二进制包内PDFium/OpenCV/GEOS/libspatialindex/BLAS/OpenMP/CUDA等NOTICE和许可可能与Python wrapper不同，未下载无法完成内容复核。源码包构建脚本执行不在当前权限；禁止为缺wheel临时编译/安装系统库。

## 许可证与安全

license-and-platform-inventory.json覆盖每个观察节点。MIT/BSD/Apache也需保留版权/NOTICE并检查专利/再分发义务；certifi的MPL、tqdm双许可、crc32c的LGPL及NVIDIA等条款需特定分发模式复核。UNKNOWN许可阻断，不能从项目名推断。pypdfium2及numpy/torch等聚合许可证尤其需逐bundled组件审查。PyPI漏洞条目为空不代表安全扫描通过；尚无完整SBOM、漏洞数据库交叉审计或artifact attestation验证。

不批准MinerU默认引入，不以Docling/MIT概括模型或所有依赖。商业部署/SaaS/镜像分发都需指定方式审核；本轮仅形成信息与阻断清单。

## 模型权重与隐藏下载

model-metadata.json来自HuggingFace对应项目组织的API，记录候选repo不可变revision、模型卡声明license、每文件git blob/LFS SHA256/size；没有获取权重payload。Docling版本源码默认layout revision仍可为main，必须在后续批准清单替换为精确revision；相关[版本源码](https://raw.githubusercontent.com/docling-project/docling/v2.145.0/docling/datamodel/layout_model_specs.py)与[离线模型路径说明](https://docling-project.github.io/docling/usage/advanced_options/)作为依据。PP-OCRv5是显式比较候选，不宣称等于3.7.0最新默认（默认/模型变更需再次查明）。[Paddle安装文档](https://www.paddleocr.ai/latest/en/version3.x/installation.html)不能替代具体模型文件验收。

| 候选仓库 | 观察revision | 声明license | 文件数 |
| --- | --- | --- | --- |
| docling-project/docling-layout-heron | 8f39ad3c0b4c58e9c2d2c84a38465abf757272d8 | apache-2.0 | 6 |
| docling-project/docling-models | 2199320848bb9a8a519d22e4b528185a4f9a6f64 | ['cdla-permissive-2.0', 'apache-2.0'] | 8 |
| PaddlePaddle/PP-OCRv5_server_det | ca867c897ecbca8873081573a802ad70d499cb94 | apache-2.0 | 6 |
| PaddlePaddle/PP-OCRv5_server_rec | b26c3587fda8da3c8ec0ce357214b4d661ff1558 | apache-2.0 | 6 |

这些候选不足以证明全部layout/table/OCR/tokenizer/config下载闭包；Docling旧table模型仓库与新stage选型匹配尚待核实。每个选用模型还需revision/model card/第三方训练或分发限制审核，批准文件精确列表和总字节上限，下载后真实hash复验，离线cache预装并禁联网启动证明无隐藏下载。缺任何文件或license则BLOCKED，不允许程序临时从huggingface/modelscope/BOS自动取回。所有实时推理/吞吐/准确率结果为NOT_RUN。

## 安装申请闭包

交付可审计的候选/传递声明/精确文件hash索引、模型元数据和明确缺口，不交伪requirements锁。闭包解除条件：每目标平台求解全部marker/extra与约束 → 精确wheel与系统库清单 → NOTICE/模型许可复核 → 容量与网络预算 → 非作者审查 → 人类专项批准。现阶段没有满足可执行安装授权的完整集合；相应工作BLOCKED，其他已授权stdlib实验正常完成。
