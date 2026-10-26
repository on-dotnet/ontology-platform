# Monaco 0.57.0 内嵌 DOMPurify 独立安全调查

2026-10-26 UTC；只读quality_reviewer，检查时Head=4d5709cc4c529ce3f91a4f9977b2ecbda56371ee。结论：PAUSED_BY_USER / BLOCKED；未安装、修改产品/锁/依赖、调用付费服务或实施patch。C0/I1/M0中的I1是dependencies.md历史override提案不充分，Master现明确将其标为已否决/不能单独修复，关闭文档缺口；Monaco仍未修复。

## 官方发布代码实证

直接读取官方npm归档并在内存解包，非仅查audit。归档18572937字节，SHA256=3ea1712fbacd3290cf4751007e3a5b57cc279767607812d4c3e57925fb0b05c2，SHA512与registry integrity一致。package/esm/vs/base/browser/dompurify/dompurify.js为133102字节，SHA256=493e9f430fbdde595f9e12ff46aa5b3606a514d5c8556eb144da69612f77fc8e；第1行许可标注3.4.15，第473行DOMPurify.version为3.4.15。domSanitize.js第4行相对导入此内嵌文件；本地残留min/vs/editor-BdtEMBbM.js、dev/vs/editor-CLplJsAh.js也含3.4.15标识。因此pnpm overrides只改变声明依赖不足以修复实际内嵌代码。

本次npm完整metadata：latest=0.57.0、next=0.57.0-rc.2，正式版本最高0.57.0；未验证到官方已修正式Monaco。官方Issue #5517仍Open，社区postinstall评论不是维护方正式修复。不自动升级或使用Preview。DOMPurify自身3.4.17已正式修复关联Critical/High公告，但具体漏洞需要相应配置、DOM输入/hooks等前提；本次未确认Monaco或当前产品可被实际利用，不能直接判当前产品Critical XSS。

官方来源：

- [npm元数据](https://registry.npmjs.org/monaco-editor)与[0.57.0归档](https://registry.npmjs.org/monaco-editor/-/monaco-editor-0.57.0.tgz)
- [Monaco CHANGELOG](https://github.com/microsoft/monaco-editor/blob/v0.57.0/CHANGELOG.md)、[0.57.0发布](https://github.com/microsoft/monaco-editor/releases/tag/v0.57.0)、[Issue #5517](https://github.com/microsoft/monaco-editor/issues/5517)
- [DOMPurify3.4.17](https://github.com/cure53/DOMPurify/releases/tag/3.4.17)、[Critical公告](https://github.com/advisories/GHSA-cg2g-xh64-v4q7)、[High公告](https://github.com/advisories/GHSA-mrv2-3pqr-j5jr)

## 当前产品和最终Next.js产物

只读Python逐文件扫描：apps/web/package.json、pnpm-lock.yaml、node_modules/.pnpm/lock.yaml中Monaco/DOMPurify名称均0命中，两份锁SHA256均9c0c20bf43a8d664026e0d8b0beb40a8ee03d3e6f0b215ebc8fbb89b267dafe8。产品源码相关导入0，Web直接symlink0。未读取或输出环境变量。

.next全部301个普通文件、50412384字节，monaco-editor、dompurify、DOMPurify、SAFE_FOR_TEMPLATES、_scrubTemplateExpressions、sanitizeSurvivingStalePolicy、3.4.15、3.4.17均0命中。BUILD_ID=7CICerMGcK9v9nFzCprSG；路径/大小/SHA256清单整体SHA256=bd5f513efd7b3ae24ae8c440602a9183312a17a18d0a95bd23cd2f794b459c71。只是有限静态产物检查，不能替代未来修复版的构建/安全测试。

本地.pnpm/monaco-editor@0.57.0与.pnpm/dompurify@3.4.15残留缓存仍存在，不属于当前锁图，不能声称整个node_modules没有旧包。缓存不读入Review源码包，不执行原地修改或删除用户缓存。当前无Monaco运行版本；未因audit零命中宣称其漏洞已修复。

## 基础源码编辑与正式语义校验

source-editor.tsx使用受控textarea和同一SourceBundle；workspace.tsx仍走正式saveDraft/validateDraft并绑定revision/hash。OntologyService保存前调用runtime.AnalyzeAsync；JenaSemanticRuntime先RIOT解析、限制OWL支持子集，再执行官方Fuseki SHACL并读取sh:conforms；报告/发布绑定revision/hash，不能用客户端伪造conforms。已读真实SEM69/69零skip及浏览器live_jena_shacl/ui_real_shacl_conforms/r2_real_shacl PASS证据；此次安全调查未重跑产品测试，不将已有语义子集称为完整OWL逻辑推理。

## 可重复patch候选设计（未实施，不构成新授权）

优先未来经实际归档核实的官方已修正式版；没有时才研究精确monaco-editor@0.57.0的pnpm patch，提交可审查patch并以patchedDependencies精确版本、lock patch hash绑定。用官方DOMPurify3.4.17 ESM替换真正内嵌实现，保留许可和相应source map；声明依赖也须精确对齐。清点ESM/min/dev所有副本，若分发min/dev须同步修复相关bundle；不能只改ESM或package.json就称整个包已修复。全新隔离恢复+frozen lock自动重现，不匹配必须失败，禁止直接改node_modules/postinstall当可审查修复。

官方DOMPurify3.4.17归档SHA256=056cbdae276897208b88c21d1d779adfa09ad7be488a2f510a28e900d3bbffe7；dist/purify.es.mjs SHA256=60c5d5ccbb466de3de3ba863461a92bf134f8c156cef7992da43e0f659bc5cbd，版本/default export已核实。机制依据：[pnpm patch](https://pnpm.io/cli/patch)、[patch-commit](https://pnpm.io/cli/patch-commit)。当前没有实施或批准恢复该候选；新增直接依赖/替代方案仍先审批。

## 修复验收矩阵

| 项目 | 状态 | 原因 |
|---|---|---|
| 官方代码/Issue/内嵌版本调查 | PASS（只读调查） | 直接归档、源码相对导入及官方元数据核实 |
| 当前锁与Next.js无Monaco检查 | PASS（有限静态范围） | 上述锁/301产物扫描，不是XSS认证 |
| Monaco修复后依赖安全扫描 | NOT_RUN | 保持暂停，无候选修复引入 |
| 修复产物实际版本/漏洞sink检查 | NOT_RUN | 没有修复版构建 |
| XSS正反回归 | NOT_RUN | 没有实现候选；不得靠audit替代 |
| 编辑器SSR/懒加载/worker兼容测试 | NOT_RUN | Monaco未接入 |
| Monaco修复同Head CI | NOT_RUN | 普通G2 CI不冒称修复专项通过 |

以上修复门禁全部通过前Monaco仍BLOCKED；不降低OWL/SHACL语义门禁，其他G2继续，完成唯一ZIP后停止。

独立原审查员限定复核：已亲读此报告和dependencies.md修正，C0/I0/M0，I1文档缺口关闭，可纳入封包；Monaco仍PAUSED_BY_USER/BLOCKED，修复专项全部NOT_RUN。未重新开展产品测试或网络调查。
