# 标准审查包合同

适用当前及后续已授权阶段。构包成功仅证明此工具执行的完整性检查成功，不表示任务、产品、CI或全面安全审计通过。Owner为工作项A；根verify和CI由Master接入。没有新增第三方依赖，仅使用PowerShell7、Git和.NET内置ZIP/散列API。

## 创建与重开

先提交全部交付内容，使工作树与未跟踪资料干净，然后使用完整40位小写提交SHA：

```powershell
pwsh -NoProfile -File scripts/create-review-package.ps1 -BaseSha <完整Base提交SHA> -HeadSha <完整Head提交SHA> -TaskId G1-INFRA-001 -Status PARTIAL -EvidencePath docs/evidence/G1-INFRA-001/validation.json
pwsh -NoProfile -File scripts/create-review-package.ps1 -Root <仓库根目录> -VerifyOnly -PackagePath <ZIP绝对路径>
pwsh -NoProfile -File scripts/tests/ReviewPackage.Tests.ps1
```

Base/Head/TaskId/Status必须明确提供。Root默认脚本所在仓库；EvidencePath可省略，但验证项将明确NOT_RUN，CI为NOT_VERIFIED。EvidencePath必须精确对应Head中的已提交文件；绝不从当前磁盘读取未提交源码或命令证据。CI可用四个显式参数一起提供：`-CiRunId`、`-CiRunUrl`、`-CiCommit`、`-CiConclusion`（success/failure/cancelled/timed_out/action_required）。它们覆盖证据JSON中的ci，记录在manifest.runtimeCi及规范化validation中，用于避免已提交文档必须预知自身Head SHA的循环。未提供时保留证据JSON的ci或NOT_VERIFIED。Base必须为Head祖先，两者必须为commit本身，不接受分支表达式。分支记录为构包时当前工作树分支，快照提交以HeadSha为准，不要求当前检出恰好Head。完整差异固定Base至Head，不依赖origin/main。

输出固定为Git忽略的`artifacts/reviews/OntologyPlatform-Review-<TaskId>-<12位Head>.zip`。同名输出存在时拒绝覆盖。仅成功复检后才将同目录`.partial`原子重命名为ZIP；失败移除工具自己创建的partial，不删除已有交付。正常命令输出一条JSON，包含确切绝对路径、sizeBytes、sha256、taskStatus及真实verification结果；退出0仅表示构包/复检成功，退出1为拒绝或异常。ZIP不提交，不上传第三方网盘。

## 文件与完整性

- `REVIEW_SUMMARY.md`：中文范围、验证状态、阻断/未运行说明及当前关口停止要求。
- `manifest.json`：schemaVersion=1、taskId、完整baseSha/headSha、当前branch、UTC date、显式status、逐项checks、ci、Git命令/退出码、diffCheck、sourceMembers映射和excludedIgnoredPaths。
- `git/changed-files.txt`、`diff.patch`、`commits.txt`、`status.txt`、`diff-check.txt`：完整binary/full-index差异、提交详情、实测干净状态及diff-check退出码。禁用外部diff/textconv，无改动时patch可为空，且Base/Head仍明确。
- `source/`：Head的完整常规Git文件树，包含隐藏配置、中文Markdown、源码、脚本、任务、ADR及原始证据；保留仓库相对路径与文档导航。
- `docs/`：原docs文档便捷副本（证据见evidence）。`evidence/`：原docs/evidence便捷副本及`validation.json`规范化状态。原始完整路径仍可在source中找到。
- `SHA256SUMS.txt`：每个其他ZIP成员精确字节的SHA256；校验和文件不自校验，整个ZIP的SHA256由最终JSON给出。

源码先由`git archive <HeadSha>`生成，再与`git ls-tree`的每个Git blob SHA1比较，防止export-ignore遗漏或export-subst改写。符号链接、submodule及非普通blob拒绝，不能悄悄漏包。重开ZIP校验全部路径、大小写冲突、链接属性、精确成员集合、全部SHA256、sourceMembers，以及从Git重新推导的完整源码和Base/Head差异。篡改payload并重算校验和仍不能绕过与Git提交的比较。ZIP时间戳固定；manifest的生成时间/机器事实使整个ZIP不承诺跨机器字节完全相同。

## 状态证据

EvidencePath示例（以下是格式说明，示例不代表命令实测）：

```json
{
  "checks": [
    {
      "name": "application-build",
      "command": null,
      "status": "NOT_RUN",
      "exitCode": null,
      "output": "环境未满足，未运行"
    }
  ],
  "ci": {
    "status": "NOT_VERIFIED",
    "runId": null,
    "url": null,
    "commit": null,
    "conclusion": null
  }
}
```

check状态支持PASS/FAIL/PARTIAL/BLOCKED/NOT_RUN/NOT_VERIFIED。PASS项必须有command、exitCode=0和非空实际输出摘要；这些是证据的结构约束，工具不重新执行用户给出的任意命令，也不查询GitHub，不能证明人工填写或显式传入事实真实。调用者须先读取实际Actions运行，再提供runId/URL/commit/conclusion；测试使用的CI字段仅为隔离模拟。CI的PASS/FAIL必须提供GitHub仓库Actions runId/URL/commit/conclusion；总PASS还要求所有check为PASS、diff-check=0、CI为PASS且commit=Head。PARTIAL/BLOCKED/NOT_RUN可以保留未知CI和未运行项，不把未知升级为成功。不得用零应用测试或静态配置检查宣称产品PASS。

manifest.archiveVerification在封包时为NOT_VERIFIED，因为最终重开尚未发生；命令返回的verification是封包后实际结果。Master应将成功命令JSON和退出码保存至下一次已提交证据（最终阶段包也可由外部交付记录证明），不得将该字段伪写为事前PASS。

## 输入与安全边界

任何tracked修改、暂存改动或非忽略untracked文件都触发DIRTY_TREE，不允许静默遗漏。忽略项仅记录路径，不读取内容、不打包；需交付的忽略文件必须先审核、调整忽略策略并依法提交。只报告排除不表示它们已验收，尤其不能把未提交测试日志当作包内证据。

禁止Git元数据、环境/认证文件（安全`.env.example`例外）、SSH、auth、`.codex/auth*`、常见密钥、数据库/备份、模型、可执行/压缩产物、机器日志、依赖及编译缓存、工具目录和artifacts。路径拒绝绝对路径、反斜线、冒号、控制字符、空段、`.`/`..`、尾空格/点及大小写冲突。输出目录在创建子目录前拒绝链接，防止写出工作树。已提交禁止项直接停止，不通过清理静默改变交付范围。

有限模式扫描覆盖所有源码字节的UTF8/UTF16解码、完整patch（包括被删除值）、提交消息及生成/重开成员。命中疑似值时只输出检查位置分类，不输出原值。该检查不能全面发现未知秘密、二进制隐写、私有数据或未经授权生产数据，也不扫描全部历史提交，独立Reviewer仍需人工审查。发现真实秘密应先修复并依法处理泄漏历史，再重新交付；本工具不自动改写历史。

## 验证入口与隔离

测试脚本建立临时Git仓库，提交真实Base/Head并调用实际CLI，验证正例、非祖先、脏树、未跟踪资料、禁止目录/文件、合成token、仅在被删patch中的token、ZIP篡改与路径注入。全部值为人工合成，不读取用户凭证。夹具清理仅限其生成且经绝对路径边界校验的系统临时目录。测试成功返回正常流程，失败throw；Master可用`& scripts/tests/ReviewPackage.Tests.ps1`接入verify和CI。必须保留实际测试数、命令和退出码，不把测试入口存在视作执行通过。
