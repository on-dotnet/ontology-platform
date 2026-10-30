# 独立Review P1修复：身份未提交状态保护

原缺陷：右侧StructuralForm blocked仅包含busy/source dirty/vocabularyPending，遗漏identityPending；身份表单或队列有内容时仍可能结构保存并accept新revision，导致子表单remount丢失本地编辑。独立Reviewer提出，Owner复核确认。

修复：父工作区使用统一structuralPending（词汇与身份时间）构造structuralWriteGate，显示禁用和onEdit实际回调共用同一门禁。未保存源码、任一种结构编辑、缺权限/理由/能力或执行中都不调用写入回调，拒绝时明确告知保留内容；只有显式提交/取消后新门禁才允许结构保存。

真实受影响回归：workspace-state.test.ts 9/9、0fail/0skip，包含身份表单/身份队列/词汇队列在回调被直接调用时写入数仍0、revision不变和编辑内容完整保留；源码dirty/权限/忙碌/理由/profile负例及显式取消后仅放行一次。lint、typecheck均exit0。只做TSX缩进整理，未重复完整177、Next build或SelfTest。真实浏览器“排队身份→结构受阻→内容保留”仍由Master实际执行，不以纯函数回归冒充浏览器通过。

修改范围只有ontology feature和本任务WEB证据，公共错误解释/脚本未改，原失败记录保持。独立复审尚待Reviewer实际结果，不自报关闭。
