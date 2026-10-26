# PRE-G3-HYGIENE-001 交付报告

任务READY_FOR_REVIEW / PARTIAL。本轮已执行附件允许的盘点、V2工具、符合条件的回收与治理规范；PARTIAL来自保护性保留和未运行平台/旧G2风险，不把保留资源当清理失败。最后交一个轻量ZIP后停止，不启动G3 Plan或业务功能。

## 基线、集成与验证

阶段Base=46c7a6de70b1b97c032b12a19bc27c1c54e70f4c，开工fetch main一致。G2已审实际CI40283523824双job success。H1提交284f8c6020e4cd7190fd1c13ca16457abac677da；H2提交3b51ef70888da6367c1f9b77a8b18124ff0fdce9，独立Review修复闭合、Mac54/54和SelfTest通过，实际LinuxCI40298045855双job成功后由Master快进main并push。H1 run40297492369被后继任务分支push取消，不宣称通过；首次本地H2SelfTest因新归档历史提交尾空格失败，已验证Git可重建后移除重复副本而未放宽规则。所有最终main/Head和主线CI使用最终包manifest显式40位SHA/实际runtimeCi及包后外部回执，不预知自身提交。

H2改动仅构包/盘点脚本、回归及治理证据文档；backend/apps/infra/contracts/CI/依赖锁/公共构建与.codex全部相对Base零diff，未新增第三方依赖。Mac真实临时Git54用例和SelfTest有原输出；Linux工程包含受锁恢复、完整Web/后端构建与测试，治理job包含真实PG和G2模块，由同Head实际run证明。Windows/Intel原生NOT_RUN，未把语法检查算平台通过；本轮没有重跑真实浏览器/完整AppHost栈，保留G2既有验收事实不改写。

## V2与独立审查

同一个真实H2提交：V1=35,377,295 bytes，V2=1,964,426 bytes，减小94.447%；详见same-head-size-comparison.json。不是仅zip存在即通过：重开成员集合、路径/链接/大小写/重复成员、checksum、source blob、完整text diff、二进制双侧与历史index均从Git重算；伪造checksum/index拒绝。现行非证据源码完整、本任务证据全保留；原始validation只存一次；相同源内容按hash只留一个物理payload。历史1167证据/共26,856,723字节只索引，必须保留受控Git访问，不能称完整离线包。

原版V1真实构包器产生的包经新版VerifyOnly独立PASS且SHA不变。独立工具初审I1文本attributes隐藏与M1只读index改写均补RED→GREEN并独立关闭；V1示例版本参数Minor已修正。完整回执和准确脚本SHA见independent-tool-review.md。清理与实际包另有独立Reviewer，不以Master自报代替。

## 真实资源回收与保护

实际删除四旧ZIP，原总66,387,291字节；三个独有M0 JSON先逐字节归档Git后删除，实际共回收66,400,665逻辑文件字节。每个准确路径、原SHA/bytes、依据、命令/exit0和after不存在见cleanup-execution.json。原G2最后包在新已提交H2包、同HeadCI和独立重开之前始终保留。审批/CI/运行/收据事实先归档；原源码和binary patch可由固定Git重建，原ZIP本体字节不可承诺完全重造，其原SHA始终记录。不改写旧包原SHA。

分支/Worktree/Docker/缓存零删除；保留17树、所有旧枝、2个exited容器、48持久卷、3默认网络、23固定/共享镜像和全局缓存。跨机器/旧会话、cherry-pick和独有数据未知，全部DEFERRED，复查触发条件见resource-after-summary.json。Docker实际可达不是BLOCKED；只读元数据抽查而未重启栈/读卷。PG/Keycloak/Jena/RustFS开发数据和g2-master私有runtime/PFX/共享工具路径留存。主checkout六个既存DS_Store保护，tracked干净与非交付untracked保留分开报告；任务实施树交付时tracked/untracked干净，ignored工具和当前ZIP不算源码输入。

最初23树到native创建后17树（含新树）的七个G1记录变化原因未核实；本轮未发出删除，不计回收，不访问全局codex归档。du/APFS/镜像shared不能换算实物释放，物理磁盘回收NOT_VERIFIED。最终有效包后本轮自行生成比较/中间包按准确hash清理，外部末次回执后验，避免为了把自身hash写入自身而循环提交。

## 风险矩阵与停止

| 项目 | 状态 | 事实与下一步 |
|---|---|---|
| V2/Mac54/SelfTest/独立工具Review | PASS | 原始命令和准确SHA；最终包另重开 |
| LinuxCI | H2 PASS，最终以manifest实际同HeadCI为准 | 不套用旧run；最终主线两个job均须实际读取 |
| Git/树/Docker/缓存回收 | DEFERRED | 未确认引用/唯一性，零删除；保留恢复材料 |
| 旧ZIP/独有收据回收 | PASS | 七个准确文件，全部exit0；前置新包独立复检 |
| 物理磁盘回收 | NOT_VERIFIED | 只报告逻辑文件字节，不虚称APFS实际释放 |
| Monaco | BLOCKED / PAUSED_BY_USER | 仍按G2内嵌DOMPurify调查，未引入/修复/override |
| 真实LLM | NOT_RUN / BLOCKED | 不调用收费模型或云API |
| Windows/Intel/浏览器重跑 | NOT_RUN | 本轮无环境或未选择此验证，不冒充通过 |
| 生产/HA/五真实源/正式SLO | NOT_RUN / NOT_VERIFIED | 本轮不涉及 |
| G3 Plan/业务 | NOT_RUN / NOT_AUTHORIZED | 下一Master仍须新明确Plan授权 |

最终输出PRE_G3_HYGIENE_READY_FOR_REVIEW仅表示提交复审，G3未授权、ChatGPT未验收。唯一ZIP大小/散列和最终Base/Head/主线CI由封包后回执给出。

额外OBSERVED：Docker默认bridge由9f14564aa5e1变abc425df5858，before/after均3个默认网络；本轮仅发出只读Docker查询，原因NOT_VERIFIED/DEFERRED，不计回收、不更改网络。容器/卷清单相同。
