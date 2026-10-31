# 开工事实与失败记录

完整读取用户附件、根/目录AGENTS、PLANS、current-authorization、bootstrap冻结合同、M5冻结合同/任务/交接、效率/本地验证/V3/生命周期、原资源与测试证据。最新fetch成功后HEAD=origin/main=580d73e7c0fb38b94dbbed1136ee0b1d24fadc9d。原主树6个未跟踪DS_Store保留；17棵原工作树（主树+16附属），创建本轮独立托管树后18棵。无Worker；Master单写，独立quality_reviewer非作者审查。

初次git fetch沙箱拒绝写.git/FETCH_HEAD exit255，经授权升级调用exit0；无自动审批拒绝。工作树工具首次错误baseBranch参数未执行创建，按实际ref schema修正后创建。rg发现不存在.agents exit2、首次milestone=G3-M5非法exit2、正确M5检查exit0；无变更公共合同或放宽工具。新树.tools缺席的ls exit1，核实后用项目既有pnpm/pythonlibs链接及离线锁恢复391包，未升级。查不存在g2-publishing-browser入口exit2后用rg定位实际g2-full-chain，未作为产品失败。

Docker第一次sandbox权限拒绝exit1，升级只读后确认daemon未运行exit1；open -a Docker启动既有应用exit0，未重启/配置引擎。真实身份desktop-linux/Engine7a8785bb-6b6e-4ae4-8065-996f4bf83016/Server29.9.2/linux aarch64。当前宿主macOS arm64、Node24.22.1/pnpm11.28.8/SDK10.0.402、AC sleep0/display10。沿用用户先前能源设置确认，不再询问。

新runtime使用g2启动profile（现有正式全部M5服务组合）但resourceLifecycle.taskId准确为G3-M5-REVIEW-FIX-001，runId=g2-1c8100ef259a；绝非借旧G2授权/凭据。新私有runtime/PFX只在本任务.tools/security，未打包/打印秘密。第一次launcher前79ms因ignored证据目录不被正式工具接受而拒绝，无资源创建；改为本任务docs/evidence暂存，之后原机器运行日志移入ignored并提交散列索引。全新环境最终关闭；共享Fuseki由正式canonical入口复用，未修改AppHost或构建配置。

原cleanup_resources.py不接受本次新TaskId。未冒用旧任务身份、未扩公共执行器：本任务纯证据cleanup.py固定8个新卷及exact plan hash/TTL/Engine/版本/创建元数据/零引用/已提交关闭证明，默认DryRun且Apply需独立审查。旧8卷逐项保护，禁止force/prune/restart/跨任务删除。私有材料及当前审查树KEEP直到复审结束，具体回执后置。
