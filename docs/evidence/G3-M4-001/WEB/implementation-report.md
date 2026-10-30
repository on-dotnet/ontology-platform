# G3-M4-WEB-A 首个可运行切片

状态：DRAFT / PARTIAL。Owner `/root/web_a`，独立托管树及任务分支见任务卡，公共基准e0662a3；仅Slice A，无Slice B/M5/G4/G5。已读取冻结合同、最新origin/main历史授权/效率/V3/生命周期和安装Next16.4.3的use-client文档；本轮M4明确授权来自当前任务分支与人类消息，未扩大范围。未修改公共客户端/生成TS/Host/迁移/锁/Tokens/Shell/scripts。

实现：身份与时间视图默认不打开，原source和graph Smoke路径保留。真实identityTime/editIdentityTime/releasedIdentityTime客户端；请求精确四源hash+revision/command，失败重试同完整payload复用幂等键。新claim必须显式组织/厂区/来源命名空间/编号/已声明目标IRI/来源IRI，组织只读，厂区只来自草稿scope；同号目录按独立IRI保留。受控Instant/Interval支持明确时区、七位小数、未知端点，禁止Date自动进位/本机时区推断/非法UTC范围。历史身份只提供关闭或收窄终点；跨源精确旧RDF项/来源保留，多值或共享时间拒绝，不覆写原编号/目标/来源/开始时间。事件更新引用新时间IRI并保留旧资源，观察时间独立记录；事件时间IRI不能自引用。

未提交表单/批次计入父工作区脏状态，切视图保留，源码/其他结构批次暂停写入；保存成功由父accept统一接受新revision并清评估。snapshot严格匹配draftId/revision/五项hash/非Release上下文，effect卸载传播Abort，正式读回要求固定ReleaseId+manifest；真实API/范围为最终裁决。诊断保留真实source/hash/focus/path与UNKNOWN位置；结构失败不伪造成保存成功。

验证实测：离线frozen恢复391包、0下载。新增专项先19测试中18PASS/1FAIL：SSR readOnly属性大小写断言错误，修正后19/19。新增事件自引用/观察时间清空/UTC边界后完整Web177/177、0fail/0skip；lint/typecheck exit0；Next生产build exit0。期间首次typecheck因一次文本替换将类型名插入vocabularyRetry内联类型失败exit2，已修复，原记录保留。随后仅TSX换行/中文注释，不修改行为；最终生产构建包含真实TypeScript检查。自动timeline记录实际命令、fingerprint、退出与UTC/monotonic区间，未采集的首次窄typecheck时间UNKNOWN，Agent活跃/思考UNKNOWN。TSX变更行均≤200。

真实浏览器/权限/深浅主题/窄屏/保存/发布查询回滚：NOT_RUN，等待Master唯一M4真实栈进行联调；不以SSR或模型测试冒充产品纵向PASS。云CI NOT_RUN；Windows/Intel宿主NOT_RUN。没有新增依赖、收费模型、Docker或持久数据；只建立本任务Worktree、独立node_modules/Next输出与既有pnpm工具复制，ignored只元数据，资源归档由Master在集成后按原生生命周期执行。当前树ACTIVE，未清理或触碰旧树/G2卷/跨项目/全局资源。
