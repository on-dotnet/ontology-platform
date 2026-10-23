# A工作项：审查包工具交付证据

日期：2026-10-23。状态：PARTIAL，等待Master独立Review与集成。阶段和产品状态不因构包测试通过而升级。

## 授权、隔离与所有权

依据已完整读取的G1-INFRA-001 authorization-v2、任务卡、current-authorization、AGENTS、PLANS、冻结合同及适用历史基线。BaseSha为968ab2a3378427cc4f2612ddb1dbb1b60b5ce9e2；任务分支codex/g1-infra-001-review-pack；独立托管树位于`C:/Users/Administrator/.codex/worktrees/g1-infra-review-pack/ontology-platform`。源码合同、测试和包规格由A单写；根verify/CI/CPM/授权规则未修改，main仅Master集成。本工作项未委派Agent。

owned_paths仅scripts/create-review-package.ps1、scripts/tests/ReviewPackage.Tests.ps1、docs/development/review-package-spec.md及本A证据目录。无新依赖、系统配置修改、管理员操作、业务功能或外部生产写入。Git认证仅使用既有helper，未读取/显示认证材料。

## 接口与交付

构包必须明确BaseSha、HeadSha、TaskId和Status；EvidencePath仅接受Head中的已提交JSON。可选显式CI参数四项需一起提供，避免Head自引用；工具只校验结构，不远程查询或伪造CI事实。默认CI=NOT_VERIFIED。完整命令及状态语义见审查包规格。

verify/CI接入入口为`pwsh -NoProfile -File scripts/tests/ReviewPackage.Tests.ps1`；也支持通过&调用，成功返回，失败throw。CaseFilter只供定位，不允许零匹配通过。最终验收必须不带过滤运行全量。

完整源码由git archive生成，与ls-tree成员和Git blob SHA1逐一比对；source保留完整相对路径，docs/evidence提供便捷副本。已提交Base/Head、祖先关系、干净树、禁止路径、patch及源码有限秘密模式均强制检查。拒绝导出属性遗漏/改写、符号链接和submodule。重开ZIP验证成员、路径、SHA256、状态来源及原始Base/Head差异，即使重算payload校验和也不能绕过提交比对。最终JSON给出实际重开结果、路径、大小和ZIP SHA256，manifest明确保留封包时点的NOT_VERIFIED，避免事前编造重开结果。

## 实际命令与失败/修复记录

所有执行均在上述树。PowerShell=7.6.5；Git=2.53.0.windows.3。源码/证据读取命令退出0；首次git fetch因沙箱无法写共享worktree FETCH_HEAD而失败（当时单项native退出未单独捕获，不填假值），随后已授权require_escalated重试退出0。初始HEAD=968ab2a，分支正确，工作树干净；观察origin/main在随后读取时为7ba38395698ab5ee614a10ac00e5f14756dac941，不把它当作本任务差异基线。

| 实际命令/文件 | 退出/状态 | 事实 |
|---|---|---|
| tests-red.txt、tests-first-implementation.txt | ABORTED，工具会话exit1 | 测试先写，但Git辅助函数与git大小写不敏感递归；手动中断，不能当有效产品RED |
| tests-second-implementation.txt | 1 | 24例夹具因Get-Command返回多个Git路径失败，改为选择Application首项 |
| tests-third-implementation.txt | 0 | 首轮24项真实Git/ZIP测试通过 |
| tests-expanded-red.txt | 1 | 33项中1项真实失败：被删除.env仍进入patch；已增加changed-path检查拒绝 |
| tests-expanded-green.txt | 1 | 34项中1项CI模拟正例失败；诊断diff-check=2 |
| ci-red.txt | 1 | 单例复现：checks与CI均PASS，JSON夹具CRLF导致diff-check=2 |
| ci-green.txt | 0 | 只修夹具LF，保留真实diff-check门禁，CI显式元数据正例通过 |

上述文件尾部保存实际命令与退出码；中断日志另由此记录说明。完整最终测试与仓库SelfTest结果见tests-final.txt、verify-final.txt。TDD有效新增RED是删除禁止文件进入patch，修复后全量复验；早期夹具故障没有被冒充为有效RED。

## 风险、未运行和停止

有限路径/UTF8/UTF16模式扫描不等于全面防泄露；未知秘密、二进制隐写、私有数据/生产数据、全部历史提交仍需独立审查。工具不读取被忽略文件内容，清单仅报告排除路径；需交付资料必须先依法提交。大仓库使用内存快照，超大合法源码仓库需将来另做流式扩展，不为当前小型基线新增依赖。

CI实际run/URL/最终commit结论本工作项NOT_VERIFIED；模拟CI测试仅验证结构，不是远程运行。应用构建/容器/资源健康测试NOT_RUN，不属于A的写入边界。Independent Reviewer由Master安排，当前NOT_VERIFIED。A只普通push任务分支，不merge main、不强推、不清理含成果的工作树。最终阶段审查包由Master按最终集成提交生成，A样例包只能证明所标明提交的工具实测。
