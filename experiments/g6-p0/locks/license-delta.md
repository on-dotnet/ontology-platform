# 许可差异与未决项

仅审查新Lite根可达观察包，共54项；两平台名称/版本相同，wheel候选各57个。声明不是法律批准；全部wheel/native NOTICE未下载、未验证，安全扫描NOT_RUN。没有任何READY_FOR_ARTIFACT_REVIEW结论。

| 观察包 | 观察版本 | 元数据许可指示 | 状态 |
| --- | --- | --- | --- |
| annotated-doc | 0.0.5 | MIT | DECLARED_ONLY |
| annotated-types | 0.8.0 | MIT | DECLARED_ONLY |
| attrs | 26.1.0 | MIT | DECLARED_ONLY |
| certifi | 2026.10.23 | MPL-2.0 | DECLARED_ONLY |
| charset-normalizer | 3.5.2 | MIT | DECLARED_ONLY |
| defusedxml | 0.7.1 | PSFL | DECLARED_ONLY |
| doclang | 0.9.0 | Apache-2.0 | DECLARED_ONLY |
| docling-core | 2.105.0 | MIT | DECLARED_ONLY |
| docling-parse | 7.24.2 | MIT | DECLARED_ONLY |
| docling-slim | 2.145.0 | MIT | DECLARED_ONLY |
| et-xmlfile | 2.0.0 | MIT | DECLARED_ONLY |
| filetype | 1.2.0 | MIT | DECLARED_ONLY |
| idna | 3.20 | BSD-3-Clause | DECLARED_ONLY |
| jsonref | 1.1.0 | MIT | DECLARED_ONLY |
| jsonschema | 4.26.0 | MIT | DECLARED_ONLY |
| jsonschema-specifications | 2025.9.1 | MIT | DECLARED_ONLY |
| langcodes | 3.5.1 | UNKNOWN | UNKNOWN_BLOCKS_APPROVAL |
| latex2mathml | 3.81.1 | MIT | DECLARED_ONLY |
| lxml | 6.1.3 | BSD-3-Clause | DECLARED_ONLY |
| markdown-it-py | 4.2.0 | UNKNOWN | UNKNOWN_BLOCKS_APPROVAL |
| marko | 2.2.5 | MIT | DECLARED_ONLY |
| mdurl | 0.1.2 | UNKNOWN | UNKNOWN_BLOCKS_APPROVAL |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | DECLARED_ONLY |
| openpyxl | 3.1.5 | MIT | DECLARED_ONLY |
| pandas | 3.1.0 | BSD-3-Clause | DECLARED_ONLY |
| pillow | 13.0.0 | MIT-CMU | DECLARED_ONLY |
| pluggy | 1.7.0 | MIT | DECLARED_ONLY |
| pydantic | 2.14.2 | MIT | DECLARED_ONLY |
| pydantic-core | 2.50.2 | MIT | DECLARED_ONLY |
| pydantic-settings | 2.16.2 | MIT | DECLARED_ONLY |
| pygments | 2.21.0 | BSD-2-Clause | DECLARED_ONLY |
| pylatexenc | 2.11 | MIT | DECLARED_ONLY |
| pypdfium2 | 5.14.0 | BSD-3-Clause, Apache-2.0, dependency licenses | DECLARED_ONLY |
| python-dateutil | 3.0.0 | Dual License | DECLARED_ONLY |
| python-docx | 1.2.0 | MIT | DECLARED_ONLY |
| python-dotenv | 1.2.4 | BSD-3-Clause | DECLARED_ONLY |
| python-pptx | 1.0.2 | MIT | DECLARED_ONLY |
| pyyaml | 6.0.3 | MIT | DECLARED_ONLY |
| referencing | 0.37.0 | MIT | DECLARED_ONLY |
| requests | 2.34.2 | Apache-2.0 | DECLARED_ONLY |
| rich | 15.0.0 | MIT | DECLARED_ONLY |
| rpds-py | 2026.9.1 | MIT | DECLARED_ONLY |
| rtree | 1.4.1 | MIT | DECLARED_ONLY |
| scipy | 1.18.1 | 长许可原文，见per-platform-results.json及PREP原字段SHA | DECLARED_ONLY |
| shellingham | 1.5.4 | ISC License | DECLARED_ONLY |
| six | 1.17.0 | MIT | DECLARED_ONLY |
| tabulate | 0.10.0 | MIT | DECLARED_ONLY |
| tqdm | 4.70.1 | MPL-2.0 AND MIT | DECLARED_ONLY |
| typer | 0.27.3 | MIT | DECLARED_ONLY |
| typing-extensions | 4.16.0 | PSF-2.0 | DECLARED_ONLY |
| typing-inspection | 0.4.4 | MIT | DECLARED_ONLY |
| tzdata | 2026.6 | Apache-2.0 | DECLARED_ONLY |
| urllib3 | 2.8.0 | MIT | DECLARED_ONLY |
| xlsxwriter | 3.3.1 | BSD-2-Clause | DECLARED_ONLY |

langcodes、markdown-it-py、mdurl未给可用license字段，保持UNKNOWN，后续需精确版本源码/artifact许可证。certifi为MPL-2.0，tqdm为MPL-2.0 AND MIT，numpy为多许可证表达式；python-dateutil Dual License、pypdfium2及SciPy长原文须分项裁决。rtree/libspatialindex、docling-parse、pypdfium2/PDFium、lxml/libxml2/libxslt、Pillow及NumPy/SciPy/Pandas的BLAS/OpenMP/codec等bundled组件需SBOM和实际NOTICE，Python wrapper MIT/BSD不覆盖全部。

相对PREP保守standard+OCR图，当前观察根不含torch/torchvision/CUDA、Paddle及模型，未重新抓162节点。仅说明依赖轮廓收窄，不能据此豁免权重或保证CPU推理质量。models-local扩展未进行；MinerU仍禁入。PREP许可原文和模型metadata全部保持原blob。

替代doclang0.8.0仅观察声明Apache-2.0和registry SHA/size；未解析其完整闭包、未下载。registry漏洞空列表不等于安全通过。数据来源为PyPI注册元数据；内容/软件许可沿各字段，元数据访问不授予wheel再分发权。
