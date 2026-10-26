# G2 精确依赖登记与实施前门禁

2026-10-26；状态PROJECT_INSTALLED / PARTIAL；初始登记表为实施前快照，实际进展以末节为准。2026-10-26人类在本会话明确批准下述精确五组及核实的必要传递依赖，现已在项目锁中实施获批安全闭包，Monaco例外继续暂停。授权V1已确认技术方向，但第1.9/3/7节要求精确第三方版本、许可、安全/商用及用途先登记核实；本表不是兼容运行PASS。

| 精确包 | 维护者/官方来源 | 许可/商用 | 用途与边界 | 当前安全与兼容状态 |
|---|---|---|---|---|
| monaco-editor 0.57.0 | Microsoft；https://registry.npmjs.org/monaco-editor/0.57.0 ，https://github.com/microsoft/monaco-editor | MIT，保留许可/通知 | 桌面Turtle/SHACL/Diff编辑器；客户端动态加载、本地worker，不用CDN；官方不支持移动浏览器，390px用同一真实草稿textarea/表单备用 | 官方metadata/tag已只读核实，未安装；完整锁图/漏洞/SSR/worker/实际编辑性能待测，NOT_VERIFIED |
| cytoscape 3.34.4 | Cytoscape Consortium；https://registry.npmjs.org/cytoscape/3.34.4 ，https://github.com/cytoscape/cytoscape.js | MIT，保留许可/通知 | 本体/实例真实RDF投影结构图，与源码/表单同revision；布局不修改语义，不引wrapper | 自带TS类型/无runtime依赖的官方声明待锁复验；完整漏洞与性能NOT_VERIFIED |
| ModelContextProtocol.AspNetCore / ModelContextProtocol / ModelContextProtocol.Core 2.3.0 | MCP C# SDK维护团队（Microsoft协作）；https://www.nuget.org/packages/ModelContextProtocol.AspNetCore/2.3.0 ，https://github.com/modelcontextprotocol/csharp-sdk | Apache-2.0，保留NOTICE/许可 | 真实本机受保护Streamable HTTP MCP工具；共享Gateway/身份/预算，无任意SQL/SPARQL工具 | 新产品直接依赖，不把AppHost现有传递1.4.1视为产品实现；2.3.0所需AI.Abstractions>=10.11.0，实际锁/NET10及安全待PoC |
| Microsoft.Agents.AI 1.26.0 | Microsoft；https://www.nuget.org/packages/Microsoft.Agents.AI/1.26.0 ，https://github.com/microsoft/agent-framework | MIT | 最小MAF受控工具编排与Provider策略；不增加云SDK/模型凭证/费用。确定性harness清楚标识，无真实模型不能全部PASS | 已核实net10.0资产及AI.Abstractions>=10.10.1；真实恢复编译/运行/Checkpoint边界NOT_VERIFIED |
| Microsoft.Extensions.AI / Microsoft.Extensions.AI.Abstractions 10.11.0 | Microsoft；https://www.nuget.org/packages/Microsoft.Extensions.AI/10.11.0 | MIT | 统一MAF/MCP最小兼容的产品锁，避免两套不兼容AI合同；不改全局SDK | 实际闭包/漏洞/冲突待受控恢复，现有Aspire锁独立保留验证 |

新增包只限上述产品方向及必要可核实的官方传递闭包。完整依赖license/security清单与npm/NuGet实际audit在批准后恢复阶段补录。没有公开advisory不代表安全PASS。若真实恢复出现不同版本/额外产品/许可冲突，停止对应引入并报告，不静默浮动升级。

Jena优先复用已批准6.2.0镜像内置官方fuseki:shacl operation，不引新Java服务/包；原始UTF-8源保留PG/RustFS。普通SPARQL端点不是SHACL验证，必须PoC读sh:conforms。TDB2可能规范化typed literal，不能把图回读当精确源字节。RustFS先用.NET内置HTTP/SigV4受控适配PoC，不新增AWS SDK。新包审批不包含真实模型/收费服务/生产凭证。

## 人类精确批准增量（2026-10-26）

用户明确批准五组精确依赖及经过安全和许可核验的必要传递依赖，无需逐个重复申请；不扩大G2业务范围。直接包只选ModelContextProtocol.AspNetCore2.3.0（不重复直接添加主包/Core），Microsoft.Agents.AI1.26.0与Microsoft.Extensions.AI10.11.0；AI.Abstractions先保持必要传递，确需直接CPM统一时记录。其他MAF扩展直接包必须先登记包名/用途，不能自动扩大。严格pnpm锁/CPM/packages.lock，不用浮动或未批Preview。Monaco/Cytoscape客户端懒加载，真实SSR/首屏/包体积/worker兼容待验收。高危漏洞、许可冲突、必须预览版或未批直接依赖停止对应链路报告。禁止收费模型/云采购/系统安装。

## 实际恢复安全门禁：Monaco暂缓引入

OBSERVED：pnpm11.28.8实际恢复monaco-editor0.57.0/cytoscape3.34.4成功，但完整pnpm audit exit1，发现Monaco精确锁定的dompurify3.4.15有1Critical/1High/3Low（其余既有图没有命中）。真实package.json依赖为dompurify=3.4.15而非可自然升级的范围。因此按用户补充第7条暂停Monaco产品引入/打包/集成；不以未使用某种模式、源码过滤或ignore advisory绕过。

Critical GHSA-cg2g-xh64-v4q7、High GHSA-mrv2-3pqr-j5jr；官方advisory给修复>=3.4.17，官方3.4.17发布存在。历史override提案已被人类暂停决定取代并否决为单独修复方案：Monaco实际相对导入内嵌3.4.15，改变声明依赖不能证明运行代码修复。不得仅用override/audit零命中恢复Monaco。未实施该提案。真实原始结果见master/web-dependency-audit-red.json和dompurify-patch-metadata.json。

官方来源：https://github.com/advisories/GHSA-cg2g-xh64-v4q7 、https://github.com/advisories/GHSA-mrv2-3pqr-j5jr 、https://github.com/cure53/DOMPurify/releases/tag/3.4.17 。完整软件/镜像供应链不是仅audit零命中就PASS。

## 人类安全门禁决定：继续暂停Monaco（2026-10-26）

用户明确选择“继续暂停Monaco，推进其他任务”。未应用任何pnpm override；移除Monaco及DOMPurify/marked等本次带来的传递图，不将漏洞依赖提交产品锁。Cytoscape3.34.4继续按原批准执行。Monaco功能状态PAUSED_BY_USER/BLOCKED，原生源码备用编辑仅作为真实备用能力，不计Monaco验收PASS；其余SEM/PUB/QRY/MCP/MAF/SSE与FE继续。后续若重启Monaco依赖需新的安全修复批准/核实，不以当前普通执行授权覆盖暂停决定。

## 已锁定闭包与实际兼容（实施更新）

实际产品直接包仅Microsoft.Agents.AI1.26.0、Microsoft.Extensions.AI10.11.0、ModelContextProtocol.AspNetCore2.3.0；Web仅新增cytoscape3.34.4，无runtime传递包。Monaco不在产品package/锁，未用override。NuGet CPM、Agents/Api/Test锁均精确版本，实际必要新增传递（相对Base全部backend锁）13项机器清单见master/nuget-new-dependency-licenses.json；包括MCP主/Core及Microsoft.Agents.AI.Abstractions、AI.Abstractions10.11.0、AI.Evaluation10.10.0、Compliance/VectorData.Abstractions10.10.0、ML.Tokenizers2.0.0、Tensors10.0.13、Google.Protobuf3.30.2。这些为批准SDK正常解析的必要传递，不新增直接MAF扩展。SPDX全部MIT/Apache-2.0/BSD-3-Clause，未发现Preview或许可冲突；来源为受控恢复的官方NuGet nuspec，保留官方许可/仓库归属元数据，不打包缓存/认证材料。

实际NuGet新依赖闭包已知漏洞查询master/nuget-final-vulnerability.json来自api.nuget.org；无报告命中仅代表该时间数据库查询，不是供应链全认证。标准包分发许可证保留义务继续适用，Review源码包不包含重分发NuGet/npm二进制缓存。Cytoscape真实SSR客户端懒加载、实际1440/1280/390深浅主题和正式RDF工作区已通过41项真实OIDC浏览器检查，FE76/76单测及构建通过；MCP2.3/MAF1.26+AI10.11真实SDK+Gateway+PG33/33与完整浏览器102/102工具链通过。以上仍不是付费真实模型或Monaco验收；最终Head CI继续等待，不把早期兼容PoC算产品全通过。

## 内嵌DOMPurify安全调查与恢复门禁（2026-10-26）

用户补充要求已由独立安全审查Agent只读执行，完整官方Issue、版本/归档/产物散列、范围和候选patch设计见[调查报告](master/monaco-embedded-security-review.md)。官方Monaco Issue #5517仍Open，npm正式latest仍0.57.0；归档ESM实际内嵌3.4.15，min/dev亦有副本。普通pnpm overrides不足以修复。当前产品锁/源码与301份Next.js产物未发现相关代码；本机旧缓存仍存在且排除交付，不能把缓存存在当已加载或声称已彻底移除。

优先评估未来官方已修正式版；版本化pnpm patch只作为可审查设计，必须绑定版本/patch hash并处理实际内嵌及全部分发副本/许可/source map，全新隔离冻结恢复可重现。未修改node_modules、未实施patch、不扩大直接依赖审批。修复后安全扫描、实际构建代码检查、XSS正反回归、编辑器SSR/worker兼容和同Head CI全部NOT_RUN；Monaco保持BLOCKED，原生源码控件继续正式RIOT/OWL子集/SHACL校验。

此前41/102浏览器与76前端测试是早期修订证据，不是最终总数；完整cold实测为113浏览器、77前端，实际PG/Jena/RustFS/SDK测试及最终CI以master/delivery-report.md和封包runtimeCi为准。普通G2 CI不代表Monaco修复通过。
