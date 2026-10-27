# G3-M1-WEB 实施报告

状态：DRAFT / PARTIAL；源码与本地Web验证已完成，等待独立审查和Master真实组合验收。本报告不宣称M1全阶段通过。

## 冻结任务边界

- Owner：m1_web；Reviewer：由Master分配非作者只读审查。
- BaseSha：a4e677a12ee6ddf0f17add548f64c049136bd2fa。
- 最终源码Head：409d7bdaa0646338a029e1add8c4ce06b774cef8；先行里程碑7b98ef340c1f403b83ff857049e2da7cccb47e17；中间修复d9ee8ea，均已推送origin/codex/g3-m1-web。
- 分支：codex/g3-m1-web；独立Worktree：/Users/chasen/.codex/worktrees/g3-m1-web/ontology-platform。
- owned_paths：apps/web/src/features/ontology/**；docs/evidence/G3-M1-001/WEB/**。
- 只读依赖：根/目标AGENTS、PLANS、当前授权、G3-M1-001任务卡及authorization-v1、冻结g3-m1-contracts、g2-generated、g2-client、Design Tokens与现有公共UI。
- Master提供的共享client提交969080b，仅经明确派发cherry-pick为cb676f7；Web Agent未自行编辑共享client。Master集成时复用其原提交，仅取本树源码/证据提交。
- 无新直接依赖；仅执行已批准受锁Web恢复和hash锁定的PyYAML验证依赖隔离恢复。未修改锁、公共配置、生成产物、CSS公共基础、Design Tokens、合同、迁移和G2历史证据。
- 停止于M1；未接入Monaco或M2高级结构功能，未调用模型，未启动/变更后端或Docker资源，未合并main。

## 结果与边界

四源导入继续严格UTF8解码，导出使用transparent换行Blob；textarea事件仅改变换行表示而无实际文本差异时复用原始字符串。单源导入不改其它源，BOM/CRLF/混合换行/非BMP与注释保留；有效UTF8字节经字符串可精确往返。真实键入允许浏览器提供的新文本换行，不能把这一行为宣称为任意修改后的逐位置字节保存。术语源absent与空字符串分开，并有明确转换按钮；absent禁用导出和textarea。

服务端profile的20行四维能力、原因、版本、hash、ASSERTED_ONLY及共享预算完整展示，表格可键盘聚焦并在窄屏横向滚动。缺profile明确UNKNOWN。未从UI节点重建RDF，不联网加载imports；domain/range、allValuesFrom、Functional和SHACL/OWL边界有说明。

保留原G2结构表单、Validate、固定修订Diff。新增独立assessment命令和持久记录重读，显示revision、profile/源/assessment hash、阶段、预算、时间与执行器、发布资格、源定位诊断；无可靠行列显示UNKNOWN。提案复用assessment的ValidationReportId，客户端只有在当前revision、全部五hash、profile、有效期、必需阶段、完整预算及服务器eligible均满足时才启用。dirty、旧修订、变更hash、旧profile、过期、未知或失败阶段均关闭；点击时再次核验时间，服务器仍为权威。

新增同草稿固定revision四源精确比较：原始字节变化、左右hash（absent明确显示）与图等价状态分开。预算耗尽、取消及未知状态明确INDETERMINATE/UNKNOWN，不能表述为零差异。取消只终止该次请求。旧Diff保留且明确其三元组计数不代表图等价结论。

新建缓冲absent改空文件也标dirty，已先RED复现后修复。原dirty导航保护、显式丢弃、远端冲突对比、完整payload幂等保存重试、角色限制、主题Tokens和移动面板保持。新建草稿成功后清空新建缓冲，避免再次新建时错误带回旧导入源。所有本轮修改手写TSX行长均≤200字符。

## 验证事实

| 命令/检查 | 结果 | 证据 |
|---|---|---|
| 开工git status / branch / HEAD / git fetch origin | 干净、正确任务分支/Base；fetch exit0 | 派发及Git历史；未读认证材料 |
| pwsh -NoProfile -File scripts/verify-web.ps1 -Restore | PASS；77基线测试、lint/typecheck/build | 开工工具输出；Next 16.4.3 / pnpm 11.28.8 |
| Vitest首轮M1行为RED | 18项，4失败/14通过，exit1 | red-tests.txt |
| absent→空源dirty补充RED | 21项，1失败/20通过，exit1 | red-absence-dirty.txt |
| 缺失OWL阶段/未知推理模式RED | 23项，2失败/21通过，exit1 | red-reasoning-tests.txt |
| 阶段未知/失败补充RED | 20项，2失败/18通过，exit1 | red-stage-tests.txt |
| 完整Web第一次验证 | FAIL；渲染读取ref违反React lint | verify-web-attempt1.txt |
| 完整Web第二次验证 | FAIL；SSR readOnly属性大小写断言，102通过/2失败 | verify-web-attempt2.txt |
| pwsh -NoProfile -File scripts/verify-web.ps1（最终源码） | PASS；lint/typecheck、9文件109测试、Next生产build，exit0 | verify-web.txt |
| node apps/web/scripts/generate-types.mjs --check | PASS；exit0，无漂移 | generated-types.txt |
| pwsh -NoProfile -File scripts/verify.ps1（最终静态） | PASS；exit0，1786文件静态检查 | verify-static.txt |
| git diff --check / 修改TSX行长专项扫描 | PASS；exit0，超过200字符行=0 | readability.txt |
| pwsh -NoProfile -File scripts/verify.ps1 -SelfTest | PASS；exit0；8工程checker、40清理、9公开history、9盘点、54构包测试；初次缺隔离PyYAML及日志自扫描失败已修复 | verify-self-test*.txt / python-restore.txt |
| 真实API/OIDC/深浅主题/窄屏/键盘浏览器 | NOT_RUN；本树未启动主栈，不能用SSR测试替代 | Master组合验收入口 |
| PostgreSQL/Jena/RustFS发布查询回滚、G2兼容、安全负例 | NOT_RUN；SEM/Master负责 | 不以mock或Web单测代替 |
| 独立Review、同HeadCI、最终唯一V2 ZIP | NOT_VERIFIED；Master统一执行 | 不复用旧CI、不在本树另交ZIP |

已读取安装Next版本的use-client与lazy-loading指南；保留Client边界和ssr:false图形懒加载。Vitest新增32项覆盖字节、四源Blob往返/重入/单源隔离、profile20行/预算、absent/只读、修订/hash/profile/过期/预算/stage/缺失OWL阶段/未知推理模式/dirty资格及比较不确定性；组件静态输出测试不是浏览器或真实API验收。

## 资源与交接

本树由Master创建且仍含待集成源码，保护保留。任务新增可再生依赖/工具缓存已实际盘点（KiB）：.tools=567876、根node_modules=549252、apps/web/node_modules=64、apps/web/.next=45756。此为重跑前时点值，非去重总容量；未创建容器/持久数据/ZIP。待独立审查、同HeadCI及集成后由Master按本任务白名单回收，不清理活跃Worktree或历史/G2资源。

开工精确时刻与总实施耗时：UNKNOWN，未估算。可验证时间锚点：基线Web测试2026-10-27 11:16:15 +08:00；最终源码Web测试以verify-web.txt的Start at为准；里程碑Git时间见提交。独立Review/集成/环境/CI/封包耗时由相应Owner另记，当前UNKNOWN。

恢复：保留本分支及Worktree，受锁恢复命令为verify-web.ps1 -Restore；PyYAML恢复命令为python3 -m pip install --require-hashes --target .tools/pythonlibs -r scripts/verification-requirements.txt。Master顺序取7b98ef3、d9ee8ea、409d7bd及后续WEB证据提交，保留共享client原969080b，完成真实组合验收后再判断可集成状态。

最终源码为409d7bd；后续仅补本WEB证据目录。证据Head由本报告所属提交确定，避免自引用未来SHA。

最终源码提交时刻：409d7bd为2026-10-27T11:30:02+08:00；第二轮完整SelfTest亦exit0，原失败及负例日志保留。Web最终109测试开始于11:29:26 +08:00。浏览器/主栈未运行状态保持。
