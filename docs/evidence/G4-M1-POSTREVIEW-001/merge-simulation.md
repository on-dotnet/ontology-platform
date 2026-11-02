# Git集成模拟（未执行合并）

本次冻结main=d1a61daffe844475b07705797e3ad325cc3f2945，候选=d40e6ab67360cc46aadd7ec013bd514b3f61a6ea。merge-base为main，左右0/45，ancestor exit0。快进的定义是main指向已有候选提交，因此最终树必为 `007527773e9db6cf63c5411df833d17c302936b9`，不是创建新tree或合并提交。采用此祖先判定路径，merge-tree --write-tree NOT_RUN；如main分叉必须重新模拟并审批。

merge-simulation.json记录全命令/exit、前后所有refs、对象清单hash/count、26工作树HEAD/status/index hash/工作区tracked diff hash。前后完整相等。git-command-ledger.json保存实际查询列表与输出散列。只读查询没有生成对象；若未来执行merge-tree须记录新增未引用对象，不得称绝对零写。

主线层diff-check exit0，完整588路径见integration-path-inventory.json；没有G6路径。任务层在最终提交后再次计算，新工具/证据仅owned_paths；不得用本层通过替代主线产品验证。

不存在文本冲突仅由当前祖先关系成立；产品回归NOT_RUN。原49行仅继承，旧ZIP重开仅899成员归档完整性。若未来main漂移、refs/index/worktree见证不一致则停止并BLOCKED_WITH_WITNESS，不自行修冲突。
