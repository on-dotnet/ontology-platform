# SEM-A 第二测试切片

状态：PARTIAL，受影响真实语义/发布已验，待独立Review与Master实际整栈/浏览器/GATE-A/main。生产目录相对4377d049d280c8bcdcec352b427a99c90f27ca59的diff exit0；本切片不改生产/公共合同/Host/scripts/依赖/迁移。

真实Semantic全套首次214项：213通过、1失败、0skip。唯一失败是原current策略语料第20项仍预期不支持，v4已授权合法Instant所以实际conforms=true。Master明确允许精确更新该断言（保留其它19项），并补相同20-time.ttl在LegacyM3精确清单下Deploy422/Verifyfalse对照；只重跑原失败+新增对照2项，全通过。随后将profile测试从复制算法强化为冻结M3实际Release程序集独立读取的旧Current黄金hash，仅重跑该变更1项通过。当前215个独立用例的组合覆盖为原212个未变已过+3个变更/新增窄验；不宣称曾单次运行215全绿，原214失败日志保持。

真实Publishing整套64项PASS/0fail/0skip：新增v4异人审批发布、正式身份对象/Jena核验、后续草稿推进不污染不可变身份读取、从v4 clone删除有效历史拒绝、精确旧v3原清单/Hash回滚、active改为v3而固定v4 Snapshot/read仍原样；确定歧义和未知关系均阻断提案，正式身份读取不完整scope在任何对象/图访问前403。Publish测试只复用生产服务，不假造成功审批；测试直接seed旧v3仅在隔离PG/S3/Jena构造历史兼容事实。当前v4真实Run由Master整链另验，本模块只断言固定AssetVersionSnapshot，未将其冒充Run。

新增真实PG并发两独立连接同revision只一成功/一409，成功修订/命令/审计均只有一次；0/1/64/65批次边界；viewer与不完整scope先于Jena（实际调用计数零）；专用新批次按固定优先级返identity_ambiguous/identity_relation_indeterminate/time_timezone_required/time_interval_reversed，均422，未保存错误输入不伪造assessment或行号。

实际命令由同名txt/json与timeline.jsonl保存，均沿现有semantic-roundtrip.py/release-faults.py、精确canonical镜像与G3-M4-001标签。首31窄验没有无变化单独再跑；Semantic整套为稳定候选所需一次，失败后仅窄测；Pub一次64项完成后没有因Semantic测试变化而重复。两模块的产品源码/锁/构建输入保持，直接绑定4377生产目录Git tree。所有容器有准确ID/Task/Run/before-command-exit-after与强no-such诊断；本切片新7个（连首窄验共9个）均finally立即回收，无命名持久卷，无image/history新增。

计时汇总efficiency-observed.json仅覆盖采集到的命令，墙钟跨度/区间并集/累计/重叠/关键路径分列；原实现思考/活跃时间UNKNOWN，不能从聊天推测。一次原完整Semantic失败后一次受影响窄复验，另一次profile测试强化；不隐去原FAIL。云CI NOT_RUN、Windows/Intel原生NOT_RUN。未启动Slice B/M5/G4/G5。
