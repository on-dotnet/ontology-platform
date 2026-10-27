# G3-M1 FIXWAVE：I1 与 M1

状态：DRAFT / PARTIAL，源码验证完成，等待Master统一真实栈和限定独立复审；没有声明整分支通过。

## 授权与边界

- BaseSha：02763a1144f25d30cdac42c907859a8784226f49。
- 源码里程碑：f149021124b637310e5b88a91e7492bf6ded10c8。
- Owner：m1_web，原Web作者；Reviewer由Master安排，Worker未自行启动审查者。
- 独立托管树：/Users/chasen/.codex/worktrees/g3-m1-fix/ontology-platform；分支codex/g3-m1-fix，开工status干净且fetch成功。
- owned_paths：apps/web/src/features/ontology/**；backend/tests/OntologyPlatform.SemanticTests/G3BoundaryTests.cs仅中文注释和成员空行；docs/evidence/G3-M1-001/FIX/**。
- 只读依据：当前授权、G3-M1-001任务及授权V1、PLANS、根/Web/backend AGENTS、冻结公共合同；Master树whole-branch-review-initial原始发现。
- 本波只负责I1/M1；Master独占I2–I4及共享验收脚本。未编辑Contracts/Host/scripts/CI/锁/Tokens，未回写旧Web/SEM树、合并main、新造ZIP、清理资源、调用模型或启动主栈。

## I1 修复

原file.arrayBuffer完成后调用旧onChange，Workspace用捕获的整份旧state替换当前缓冲，实际能回退名称、其它源、草稿身份和revision。修复没有改成仅用最新回调ref：新增局部文件读取会话，工作区epoch隔离切换/丢弃/后发命令/会话变化/卸载，逐源generation按发起顺序隔离同源新导入或键入，开始时冻结draftId/revision。完成时再次检查票据，在函数式当前state中核对草稿身份和revision，只合并目标源；新建缓冲同样受epoch保护。

其它源和名称的后续编辑通过函数式当前state更新保留；同源后发键入、导入、设为absent会使旧读取失效。超限或非法UTF8后发导入也不会恢复先前文件。旧失败不覆盖新成功的错误状态；input选择在读取前清空，旧finally不再清除后发文件选择。未改变源解析、字节保留、服务端CAS/权限/预算或发布语义。

新增source-import-race.test.ts，调用实际SourceEditor TSX上传处理器和实际OntologyWorkspace回调，用延迟/拒绝Promise控制File.arrayBuffer。Node内只替换React hook调度及外部目录/草稿读取IO；断言针对真实用户缓冲和可见错误，未复制生产更新逻辑、使用TSX文本parser或新增JSDOM/依赖。调度器初次嵌套render错误修正后，13项均获得真实断言RED，再全部GREEN；不能把hook调度器视为真实浏览器。

13项覆盖：等待期间名称/其它源、同源新键入、同源乱序、跨源乱序、草稿切换、新revision、显式丢弃、旧草稿进入新建、隐藏新建缓冲污染、actor切换、后发超限、旧失败和卸载。原四源BOM/CRLF/非BMP、支持档案/assessment/dirty测试全部保留。

## M1 修复

G3BoundaryTests仅增加两处相邻成员空行、一行循环索引用途中文注释。没有更改任何算法、预算、测试断言或源数据；diff已人工逐行核对。dotnet format whitespace通过不代表C#注释语义由工具自动判定。

## 验证事实

| 项目 | 实际结果 | 证据 |
|---|---|---|
| verify-web.ps1 -Restore 基线 | PASS，exit0，109测试+lint/typecheck/build | baseline-web.txt |
| Vitest竞态RED | FAIL，exit1，13真实断言失败 | import-red.txt |
| Vitest竞态GREEN | PASS，exit0，13通过 | import-green.txt |
| 第一次完整Web检查 | FAIL，exit1，测试调度器active=this触发no-this-alias | verify-web-attempt1.txt |
| verify-web.ps1 -Restore 最终候选 | PASS，exit0，10文件122测试+lint/typecheck/build | verify-web.txt |
| dotnet format whitespace 指定绝对include / --verify-no-changes / --no-restore | PASS，exit0，实际工作区9文件，0文件被改写 | csharp-format.txt |
| git diff --check / changed TSX行长 / C#限定diff | PASS，超200字符行=0，C#仅三行增加 | scope-check.txt |
| verify.ps1（最终静态） | PASS，exit0，格式/相对链接等工程静态检查 | verify-static.txt |
| verify.ps1 -SelfTest | PASS，exit0；8 checker、40 cleanup、9 history、9 inspector、三组3项reader/compatibility及54 ZIP测试 | verify-self-test.txt |
| 真实主栈/browser/统一I2–I4/独立Review/同HeadCI | NOT_RUN / NOT_VERIFIED，由Master负责 | browser-race-handoff.md仅步骤，不是执行证据 |
| C# build/test及真实Jena/PG验证 | NOT_RUN，本Worker只修改注释空行，无project.assets基线且未启动主栈 | 不把format当业务测试 |

日志证据仅将stdout/stderr规范为LF、去行尾空白并保留结尾换行；原始/tmp日志及所有源字节夹具未改写、未删除。首次最小C#format的SDK首次运行/工作负载诊断保留，未运行workload update或变更全局配置。工具恢复仅用已有精确锁和批准PyYAML hash清单，未加直接依赖。

## 时间与交接

实际时间锚点：真实竞态RED 12:45:35、GREEN 12:46:58、完整122测试12:49:09（2026-10-27 +08:00）。开始/实施总耗时未计时，UNKNOWN；集成、环境、CI、审查、封包耗时由Master记录，不估算。

Master取源码里程碑及后续FIX证据提交，按browser-race-handoff.md在本轮真实授权栈复验延迟File.arrayBuffer。Worker保持任务树干净且保留可再生缓存，不做资源回收；当前关口交付后停止。任何真实浏览器或限定复审失败保留原证据，不用本地122测试替代。

源码里程碑提交时间：2026-10-27T12:50:50+08:00。完整SelfTest已真实完成exit0；后续仅补FIX证据。本报告所属提交是证据Head，禁止预填自引用未来SHA。
