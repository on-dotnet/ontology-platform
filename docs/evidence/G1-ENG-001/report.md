# G1-ENG-001执行与验收证据

日期2026-10-23，Asia/Shanghai。结论：**PARTIAL**。工程静态门禁实际PASS；目标工具链尚未满足，产品检查未运行，不能称整个G1通过。

## 授权和范围

授权原文已完整读取：`ontology-platform-G1-ENG-001-codex-master-authorization.md`，SHA256为`4F2789063613871C234EE40A102D6378F697E867A0E4E0EA74D4F0A2A0FA14F7`。用户随后明确授权阶段成果主动提交远程、无需worktree、可在main推进；仅改变Git交付方式，不扩大G1-ENG-001业务边界。

起点`codex/g0-plan-baseline` / `312209e5ad477f3219dae75f090ae18bfc2a3f9e`；创建任务分支`codex/g1-eng-001`。G0全部11份文档和bootstrap完整读取；旧计划是历史快照，不越白名单改写。提交SHA和远程交付结果以最终报告/Git历史为准，不循环写入自身提交SHA。

## 实际检查

| 命令/动作 | 退出码 | 判定与证据 |
|---|---|---|
| Git remote/branch/status/log、merge-base祖先检查 | 0 | 起点正确、工作树干净、无同名任务分支冲突 |
| `pwsh -NoProfile -File scripts/verify.ps1 -SelfTest` | 0 | JSON/XML/PS语法、文本格式、相对链接/锚点、有限机密模式、包命名/版本/workspace/CI策略和8项正反例PASS；见verify-output.txt |
| `pwsh -NoProfile -File scripts/doctor.ps1` | 2 | 环境BLOCKED，见doctor-output.txt；不是脚本误报PASS |
| `python -c`调用标准库tomllib解析`.codex/**/*.toml` | 0 | 4份TOML实际语法PASS；不是CI永久TOML覆盖或角色实例化证明 |
| 临时空CODEX_HOME运行`codex features list` | 0 | 本机CLI可执行；未触发模型调用，不表示角色已实例化 |
| 复制项目config到隔离临时home，`codex --strict-config doctor --summary` | 1 | 配置项显示loaded；总失败因刻意无认证及网络不可达。配置解析PASS，完整健康BLOCKED，不宣称项目角色实际加载 |
| `git diff --check` | 0 | 跟踪差异无空白错误；暂存范围/差异及提交状态在Git交付步骤复核 |

临时CODEX_HOME均在受控临时目录，无真实认证或MCP配置，结束后恢复原进程变量并清理；未改用户全局配置。doctor探测出现网络不可达，不是生产连接或付费模型调用。

## 检查器测试

先写测试并实际看到缺少verify实现退出1；随后实现检查器。正例为干净工程基线；反例覆盖错误包名、失效相对链接、合成token、TypeScript token、`.env`凭证、未固定Action，均在隔离临时目录产生和清理，不输出合成凭证值。

新增native cwd检查先实际失败，再修复为绝对solution + Push/Pop-Location；断言两次dotnet调用均来自选定Root，通过。该用例使用替身，不运行真实.NET构建。最终8项PASS；不将检查器测试数量当作应用测试数量。

## 工具与依赖状态

目标SDK10.0.402，本机最高10.0.401；目标Node24.22.1安全补丁，本机24.21.0；目标pnpm11.28.8，本机11.25.0。未安装OS工具或修改全局PATH。局部EF10.0.13未恢复、包元数据未验证，不调用全局EF9.0.7替代。详细官方来源、许可及安全边界见[登记](dependencies.md)。

没有真实应用依赖，不安装Turbo/Next/MSTest/Kiota/Hey API，不生成空pnpm/NuGet锁。CPM只有必要开关。无业务项目，build/test/format/E2E均NOT_RUN。CI托管运行在远程实际执行前NOT_RUN；自定义Agent实例化NOT_RUN。

`.agents/skills/verify-change`为可选项，本轮未创建：当前工程命令和项目特定规则由根AGENTS/PLANS直接路由，避免重复规则；不为填充目录制造无额外价值技能。`.codex`三角色按官方最小格式提供，继承父权限，不是OS沙箱。

## 分工与评审

- Master唯一编辑Owner：读取合同、配置/脚本/ADR/文档、运行验证、处理评审及Git交付。
- `codex_research`只读：本机CLI、官方角色/配置格式和版本证据局限。
- `toolchain_research`只读：SDK/Node/pnpm/EF/Aspire版本、官方安全/许可和Action固定SHA。
- `quality_review`独立只读：完整审查和实际复验；[完整意见与处理](review.md)。没有并发编辑。

## 剩余风险及G1-INFRA前置条件

1. 另行专用授权：尚未获得，阻止启动G1-INFRA/SEC/FE/OBS及G2。
2. 目标SDK/Node/pnpm准备：环境BLOCKED，由操作者在允许环境准备，不在本任务OS安装。
3. NuGet工具/项目依赖实际恢复、锁图和漏洞检查：NOT_RUN；首次引入前完成。
4. Docker daemon、镜像网络、RustFS/Jena/PG/Keycloak及Aspire集成：NOT_VERIFIED，本任务不启动资源。
5. 真实角色实例化、Next通用编排、MSTest/MTP及Kiota/Hey API PoC：NOT_RUN，按ADR和后续范围执行。
6. CI为受控静态任务：Runner实际兼容和远程执行结果待确认；有限模式/正则不是完整YAML/TOML解析或安全审计，保留Minor。
7. Design System物理位置ADR-001已批准，但组件/Tokens/Shell/主题/中文/无障碍实现仍属于后续任务；没有降低产品标准。

文件清单见[files.md](files.md)。本任务结束即停止，不自动启动任何其他G1任务或G2。

## Git远程前检

`git -c credential.interactive=false -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=15 ls-remote origin refs/heads/main`实际退出1：无法在禁止交互时取得密码。未要求用户输入或输出任何凭证，未改全局Git配置。已尝试可用GitHub连接器只读get_repo，连接chatgpt.com后端失败，不能借此确认远端状态。

因此远程验证BLOCKED；本地成果仍可提交、快进main，普通非force push自身将保护远端不被覆盖。最终推送结果另在交付报告说明，不因用户已授权就宣称已推送成功。

## 实际Git交付及持续授权记录

- 工程提交已生成：`2d7a352`，`chore: establish G1-ENG-001 engineering baseline`；42文件、915新增行、1删除行，G0历史文档无修改。
- `git switch main`及`git merge --ff-only codex/g1-eng-001`均退出0；main由226457b安全快进至2d7a352，包含G0归档312209e和本任务，不产生合并提交，不重写历史。
- 普通非强制`git -c credential.interactive=false -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=15 push origin main`实际退出1：`Cannot prompt because user interactivity has been disabled`、`unable to get password from user`。远程未确认更新，CI未确认执行。
- 用户再次明确“git我授权了，你记录下”。根AGENTS/PLANS已持久记录：无需worktree、默认main、阶段验证和审查后主动commit/push，不再重复询问Git授权。当前失败是GitHub认证阻断，不是授权缺失；没有读取/输出私密凭证，也不修改全局凭证设置。
- 本次授权记录补充将单独本地提交；最终SHA见交付报告/Git历史。因认证前提未变化，不将重复失败当作推送成功。

### 后续认证恢复（用户明确要求重新弹出并记住凭证）

用户再次明确要求打开GitHub凭证授权并避免以后重复弹出。执行GCM2.7.3的浏览器登录（旧凭证存在后按用户要求force重新认证），退出0；只检查GCM返回字段是否存在，不输出密码/token。发现需要明确选择on-dotnet账号，指定后ls-remote退出0，远程main为226457bfbbd1e16bd1608115a72de7682b0811ef。

已在当前仓库Git配置中绑定GitHub账号on-dotnet和manager helper，不更改全局配置、不在文档/源码存凭证。随后不显式指定helper/username的非交互ls-remote验证静默复用。根AGENTS已记录持续Git授权和不反复弹登录的偏好；凭证失效需报告，不能假称永久有效。工程缺失SDK/Node/pnpm等状态不因Git认证恢复而改变。
