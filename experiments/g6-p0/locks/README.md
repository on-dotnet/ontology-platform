# Docling Lite受限依赖观察

状态：BLOCKED_WITH_WITNESS / PARTIAL。没有requirements.lock，没有成功resolver运行；两平台solution/selectedWheel均为空。G3 main与PREP未合并，G4仍未启动。

固定根docling-slim[convert-core,format-pdf,format-office,format-markdown]==2.145.0。原始Requires-Dist来自PREP快照，当前新根重新传播，绝不继承standard/models-local或Paddle extras。format-pdf真实引入docling-parse与pypdfium2；format-office含openpyxl、pylatexenc、python-docx、python-pptx。原生PDF不等于布局/表格/OCR/Anchor质量通过。

T1=CPython3.12 Linux aarch64，T2=同minor Linux x86_64。patch、glibc、基础镜像/digest尚未冻结，不能宣称容器或运行时锁。输出只枚举已观察版本的全部条件wheel候选，保留每条PEP tag和所需glibc下限。cp312/abi3及pure-any由现有pip vendored packaging解析；不接受Mac、Windows、musl或裸linux tag作为glibc portability证据。Python patch相关marker/范围保守UNKNOWN，不借用宿主3.13。未运行目标Linux环境。

每平台54包/79声明/57条件候选文件，无观察版本缺wheel。快照冲突：docling-core2.105.0要求doclang>=0.8,<0.9，PREP观察0.9.0不满足。定向替代doclang0.8.0满足该单边、声明Apache-2.0且有py3-none-any wheel；未替换原图、未继续搜索，不能因此称完整可解或全局无解。

关键阻断是RESOLVER_TOOL_APPROVAL_REQUIRED。本机pip26.2.2的dry-run允许先sidecar metadata、再fallback到wheel下载；当前无可证零payload的求解入口，因此没有执行pip install/dry-run/lock。observe.py只对一个已观察版本逐边核验，包含PEP508 marker/extra传播、PEP440约束和wheel tags；它不搜索版本、不回溯，不是resolver。再次运行输出应与per-platform-results.json相同（输入hash明确绑定）。已有解析器来自pip26.2.2 vendored packaging26.2，未安装新依赖。

复现：python3 -B experiments/g6-p0/locks/observe.py；python3 -B -m unittest discover -s experiments/g6-p0/locks/tests -v。输出仅stdout，由调用方保存到ignored artifacts或已审证据。新文件限当前目录/任务卡/本任务证据；其它源码历史数据只读。

models-local第二轮廓为NOT_RUN，因为基线未完成；不展开torch/weights研究。PaddleOCR仍为独立OCR Worker候选，保留原PyYAML6.0.2、OpenCV4.10.0.84、opt-einsum3.3.0、numpy<2.4及权重/商用限制，不混装。wheel SHA和size来自registry声明，未下载验证，所有native NOTICE、SBOM、漏洞和模型许可仍NOT_VERIFIED/NOT_RUN。下一事项仅为install-authorization-draft.md的单项授权草案，当前不可执行。
