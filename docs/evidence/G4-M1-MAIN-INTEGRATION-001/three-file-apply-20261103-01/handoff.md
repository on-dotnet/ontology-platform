# 三文件精确修复交付

本轮仅执行已批准的精确三文件修复及必要验证。三文件修复完成不代表阶段B整体通过；不进入main更新或M2/G6。

授权文档SHA256：ed4bbf1b10ff175b5592bb2bcd3492ce46d43dd8d6a50381aa791f0ee0b75eb9。用户后续允许删除无用的单个.DS_Store，并重申仅解除三文件写入限制。该文件经文件类型、未跟踪状态、普通文件/链接计数与固定签名核实为Finder目录元数据，准确删除，其他.DS_Store不动。

SourceHead：8753fb92fa0a3375c539f192525c85a5b2fee844。ApprovedMain：d1a61daffe844475b07705797e3ad325cc3f2945。源码提交：2b5af7b81fbd78143ea2a76c787bfc2fa402e30d。新验证提交T：8c7e43ab4f8f27d231d9d83b42c96ef17a1918fe。最终H/远端绑定/唯一新V3和独立重开见本轮包外final-receipt.json。

唯一补丁31,032字节，SHA256：3443614b8dd4b7da720d5c08d781e18074d3cb06daac9cf612cc96fa60f62b20。三个路径、13个hunk、Before/隔离After/真实After均3/3精确匹配；无新增/删除/改名/模式/链接/二进制变更。独立Reviewer在真实应用前新审查该补丁，Master准确应用一次。

两份迁移仅改变namespace语法和缩进。新Roslyn检查命名空间、类型、成员、Up/Down、非命名空间token、注释、Designer partial关联和Migration ID一致；编译后反射检查两类型及MigrationAttribute ID亦一致。无迁移执行、无Down、无新模型/快照。

PgFixtureSecurityTests只移动同一动态属性赋值至builder初始化器后。新AST检查赋值来源和次数、其余连接选项、连接创建语句一致。锁定Npgsql10.0.3的六类合成输入（普通、引号/分号、Unicode、空串、null、参数冲突样式数据）有效设置一致，连接全部Closed；参数顺序可不同。此结论不是PG/TLS验收。

原样verify和V3有限扫描器均接受修复后的三个源码；合成密钥字面量负例均被原规则拒绝。原scanner/.editorconfig/公共构建/锁文件均未修改。初版负例fixture缺少基线JSON字段引发校验异常，随后只补隔离fixture必要元数据，新负例通过；首次失败和执行字节保留。

完整dotnet format --verify-no-changes --no-restore exit0，构建exit0。直接受影响测试：Connections 23通过/14跳过，Semantic 56通过/246跳过，合计339项、79通过、260跳过、0失败。每个跳过case及原因见skipped-cases.json；真实夹具没有运行。上一轮150通过/90跳过属于不同四项目历史运行，不继承，不宣称旧90已闭合。format/build/两项目测试发生于提交前精确After工作树，原回执HEAD仍保留8753，实际源码字节与新T相等；不改写执行历史。

首次新静态检查暴露上一轮0字节原始日志的格式约束：旧exact-format-verify.txt缺末尾LF。经独立Review，以archived-empty-log.json无损保存原路径、原0字节、SHA和8753 Git blob恢复入口，原ignored副本不动，原exit -9/中断结论不变。新T仅在三文件源码提交之后追加此证据表示调整。旧索引和回执仍按8753历史快照解释，旧路径通过归档映射或原Git对象恢复；未给原日志补换行、未改共享格式规则。原静态入口随后exit0。

宿主边界4测试通过。新T完整SelfTest实际exit0，27/27套通过，运行430.6056477079983秒；ReviewPackage子套件103项0失败。结果在validation.json和raw-output.json中记录；没有用过去27套结果替代。执行脚本被逐字节归档，记录器散列与被执行脚本散列明确区分。AST重放需要原SourceHead的Before快照和批准After副本，不能在已变更live文件上误重放后宣称结果改变。

I01仅本轮工程修复验证完成，完整Web和真实夹具门禁仍未闭合；I02–I07 NOT_RUN；I08仅本轮PARTIAL交付，不满足READY_FOR_CHATGPT_MAIN_MERGE_APPROVAL。任务适配器仍为历史DRAFT/未完成，本轮未扩大适配器写入。CI/Windows/Intel NOT_RUN；AMBER-A1/LICENSE_PARTIAL和完整供应链未验证限制不变。

只读使用已核验本地工具，离线锁定restore使用独立任务缓存，下载/费用/GPU为0；没有产品容器、源库、OIDC或真实浏览器运行。三文件差异和原始失败全部保留，最终仅回收本轮白名单可再生资源。保留本任务分支/工作树、证据、原e7e6阻断ZIP及新唯一V3，解除条件为后续明确集成与生命周期批准。恢复入口为新T和本任务原计划，先重新准入本地缓存与资源，不能安装/下载或自动进入下游。

资源收尾实测：48个可再生目录、9708普通文件、2,187,081,625逻辑字节，逐项ENOENT，4474跟踪文件散列保持；不等同APFS物理空间释放量。精确监测PID80743已释放exit0，98次心跳，锁屏0次，displayOff/sessionContinuity仍NOT_VERIFIED。
