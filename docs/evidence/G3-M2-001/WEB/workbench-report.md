# G3-M2-WEB 第二切片

状态：PARTIAL，待Master真实OIDC浏览器与独立Review。Owner/路径/基线同slice-report.md。
UTC命令区间：2026-10-27T14:27–14:34Z为实现/测试；工时UNKNOWN，不从聊天推断。初次SelfTest缺隔离PyYAML导致structured-syntax FAIL/exit1，原始失败见ui-selftest.txt；已只读链接Master批准的隔离pythonlibs后重跑，仍运行中，不提前写PASS。

实现左侧资产及类/对象属性/数据属性/个体分组，中间图/源码切换，右侧所选属性/精确编辑/四状态/诊断/版本比较。原Shell、Tokens、四源导入与CAS路径保持；Monaco仍暂停。结构编辑成功后自动读取服务端Diff，仅修订和bundle hash对应时展示；其他三源从完整服务端响应读取。草稿ID/revision和节点/hash共同重置结构表单。

四状态独立展示可保存/可结构编辑/可发布/可推理；profile未知或未授权/dirty时关闭结构命令。发布资格由原assessmentEligibility校验完整修订/四源散列/profile/预算/阶段/有效期，OWL_REASONING保留NOT_RUN。
诊断中文解释并保留原message/code/focus/path/sourceShape/hash。只有当前单源hash可定位，dirty/未知来源/bundle拒绝跳转；focus必须存在于实际投影。blank shape不显示猜测行列；命名shape仅作为证据，未取得精确源节点绑定不定位shape。服务提供可靠行列时还检查当前原文边界。

验证：先四状态组件断言RED及diagnosticLocation缺实现RED（原日志保留），随后GREEN。最终Vitest 13文件139项通过、0skip；lint/typecheck与Next16.4.3真实build均exit0。编译路由包含ontologies/releases/analysis；不等于真实OIDC业务PASS。TSX此次触及文件每行≤200。归档日志只规范化终端CR/行尾与EOF单LF，ignored artifacts保留原始输出；未删除失败。

浏览器入口：左region=本体实体树，节点button aria-pressed；中region=草稿源码，默认源码视图，按钮图视图/源码视图；右region=结构与验证。新增所选实体属性/精确结构编辑/建模能力四状态/结构编辑 Diff；诊断aria-label=评估诊断1，data-source-current表明单源绑定，定位诊断来源 1按钮仅可靠来源存在。原结构操作/主体IRI/结构谓词/新对象类型/新对象值/结构编辑三元组/提交真实结构编辑与四源label全部保留。

建议真实闭环：打开资产→填写变更理由→左树选择已声明Class→新增→equivalentClass或disjointWith→受控主体与对象→提交→确认revision、真实Diff及重读；对象属性以inverseOf同样验证。再切换节点/修订验证对象重置；选择语言label三元组执行remove并核对旧对象datatype/language；源码dirty关闭结构与发布→保存→重评估。复杂图仍可源码编辑/原文导出但结构只读；诊断只按可靠来源跳转。

资源：没有Docker/运行时资源；本树node_modules约537MiB、apps/web/.next约45MiB均可由锁定pnpm离线install及build再生；.tools/pythonlibs仅指向Master同任务既有批准隔离解析包。KEEP至当前独立Review、同HeadCI及Master确认集成，之后按主任务精确白名单处理。未清旧树或共享store。

后置实测：2026-10-27T14:38Z，恢复隔离PyYAML后的完整 `pwsh -NoProfile -File scripts/verify.ps1 -SelfTest` exit0，证据ui-selftest-restored.txt。清理执行器44项通过，ReviewPackage 96项0失败；其余checker/orchestration/结构化解析回归以实际日志为准。首次工具资产失败保留ui-selftest.txt；未把工程检查当浏览器业务或.NET产品测试。此后只有证据更新，源码保持第二切片8d93a7844f4b9b1bcb91044866ccb0366ff007f5。
