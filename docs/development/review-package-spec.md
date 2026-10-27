# 标准审查包合同 V3

## V3 默认 compact 合同（G3-M1-CLOSEOUT-002）

人类2026-10-27正式授权本轮工程纠偏，默认创建 `schemaVersion=3`。历史V1/V2的格式和原始ZIP/SHA保持；`VerifyOnly`按manifest版本分派，显式 `-SchemaVersion 1` / `2` 仍可创建历史格式。下面V2/V1章节仅适用其对应版本，不扩大V3。

V3包含 `REVIEW_SUMMARY.md`、`manifest.json`、`SHA256SUMS.txt`、`git/diff-text.patch`、`git/changed-files.json`、`git/commits.txt`、`git/diff-check.txt`、`git/status.txt`、`git/ci.json`、`source/`、`review-evidence/`及`evidence-index.json`。完整现行非证据源码/配置/测试/合同/ADR和当前任务非PNG证据全部从已提交Head读取，按SHA256只存一次payload；禁止在source下再复制docs/evidence。历史证据及省略PNG逐条保留commit、blob OID、SHA256、size、path、恢复入口；Base/Head所有文本差异完整保留，二进制变更两侧的OID/hash/size/mode/状态完整列在changed-files。恢复省略字节需要精确Git对象访问：**Slim不等于独立离线审计包**。Git原始证据不删除，不以缩包隐藏关键失败。

代表截图必须由Head中 `docs/evidence/<TaskId>/review-screenshots.json` 显式声明；没有清单时不复制任何证据PNG（仍完整索引可恢复）。允许选择历史任务中的最终稳定证据。格式：

```json
{
  "schemaVersion": 1,
  "screenshots": [
    { "path": "docs/evidence/<TaskId>/stable/page.png", "page": "关键页面", "theme": "light", "viewport": "1440x900", "stable": true }
  ]
}
```

每个页面/主题/视口最多一张，路径唯一，最多12张；不同PNG payload的Deflate压缩总量不得超过3MiB。重复、非稳定、未提交、非PNG、超预算选择均拒绝。无UI变更无需新增截图，不将过程截图自动升级为正式交付。

ignored只读取有限文件长度元数据，不读取内容、不跟随链接；manifest使用 `ignoredInventory` 替代全量 `excludedIgnoredPaths`，按有限顶层目录/类别保存count、estimatedBytes、unknownSizeCount、最多两个示例、清单SHA256及扫描UTC时间。完整NUL分隔路径清单仅存本地ignored artifact，绝不随ZIP传播。体积估算不是物理容量或内容验收。忽略项在之后可能变化，重开只验证交付payload和Git恢复索引，不将ignored快照宣称为可从ZIP恢复的交付输入。

V3创建和VerifyOnly都实际执行 `gh run view <runId> --repo on-dotnet/ontology-platform --json databaseId,headSha,url,status,conclusion,jobs`。使用OS凭证helper，不读取认证材料。要求实际run ID/URL/Head精确一致、run已完成，且 `engineering`、`governance-integration` 各恰好一个已完成job，记录job ID/URL/结论。run成功而任一必需job失败也拒绝；手工success不能代替API实查。创建时仍以四个显式CI参数一并提供选择和待核对事实，或从已提交EvidencePath读取runId。重开重新查询GitHub并比较原结果，网络/权限不足则明确失败，不能提升为PASS。

```powershell
pwsh -NoProfile -File scripts/create-review-package.ps1 -BaseSha <40位Base> -HeadSha <40位Head> -TaskId <任务ID> -Status PARTIAL -EvidencePath docs/evidence/<任务ID>/validation.json -CiRunId <真实run> -CiRunUrl <真实URL> -CiCommit <同Head> -CiConclusion success
pwsh -NoProfile -File scripts/create-review-package.ps1 -Root <干净实施树> -VerifyOnly -PackagePath <唯一ZIP绝对路径>
pwsh -NoProfile -File scripts/tests/ReviewPackage.Tests.ps1
```

原始 `EvidencePath` JSON中只有顶层 `checks` 和 `ci` 进入规范化状态对象，参与manifest状态与重开比较；所有现行校验仍检查原checks/ci，实际查询的同HeadCI只覆盖规范化ci。未知顶层字段（如note、嵌套context）是非权威metadata，不进入规范化状态、不影响PASS/FAIL。原始JSON完整字节及其附加metadata仍从Head按原blob/hash/size保留：V2/V3以单份payload映射恢复，V1继续历史source/证据便捷副本合同；不能通过删除原文metadata使构包偶然成功。V1的 `evidence/validation.json` 只存规范化checks/ci。FAIL检查不会被metadata中的PASS文字掩盖，总体PASS仍要求全部检查、diff-check及同HeadCI满足既有门禁。

V3要求Base为Head祖先、tracked/untracked干净、完整Base..Head `git diff --check` exit0。拒绝不安全路径、大小写冲突、链接/submodule、秘密模式命中、被删秘密、伪造CI/散列/索引；独立重开重新推导源码blob、证据索引、二进制元数据和完整文本diff，不接受重新计算ZIP校验和后的篡改。原子`.partial`通过复检后才发布，失败移除自身partial并保留上一有效ZIP。

软目标≤10MiB；超10MiB的CLI JSON必须输出按source/review-evidence/git/metadata-and-index分类的实际压缩/原始字节和ZIP开销。默认硬门禁15MiB，超过即拒绝发布和V3重开，不静默放宽；当前实现无绕过开关。若后续任务需要特例，先记录经独立审查的具体合同和受限工具变更，再实施。唯一ZIP仍在ignored `artifacts/reviews`，不提交Git。

回归通过真实临时Git和ZIP验证V1/V2兼容；V3的53张不同PNG、55,256条实际ignored路径、单份payload、精确Git恢复、伪造CI及jobs、文本/索引/hash篡改、缺失索引、脏树/未跟踪/非祖先/路径/大小写/链接/秘密、截图和10/15MiB门禁。测试GitHub查询仅在系统临时fixture进程PATH注入fake gh，不构成实际GitHub CI成功证据。生产工具没有接受fixture CI的参数。

---

## V2 历史兼容合同


本次由PRE-G3-HYGIENE-001授权升级；默认schemaVersion=2 compact reviewer package。schemaVersion=1的历史格式、原ZIP和历史SHA不改，VerifyOnly按manifest版本分派，创建V1需显式`-SchemaVersion 1`。无新增直接依赖。构包成功仅证明有限完整性检查。

## V2 创建、重开和结构

先提交全部交付，使实施树tracked/untracked干净，明确40位Base/Head且Base为祖先：

```powershell
pwsh -NoProfile -File scripts/create-review-package.ps1 -BaseSha <40位Base> -HeadSha <40位Head> -TaskId PRE-G3-HYGIENE-001 -Status PARTIAL -EvidencePath docs/evidence/PRE-G3-HYGIENE-001/validation.json -CiRunId <实际runId> -CiRunUrl <实际runURL> -CiCommit <同Head> -CiConclusion success
pwsh -NoProfile -File scripts/create-review-package.ps1 -Root <干净实施树> -VerifyOnly -PackagePath <ZIP绝对路径>
pwsh -NoProfile -File scripts/tests/ReviewPackage.Tests.ps1
```

包含REVIEW_SUMMARY.md、manifest.json、SHA256SUMS.txt、git/commits.txt、git/changed-files.json、git/diff-text.patch、git/diff-check.txt、git/status.txt、git/ci.json、source/、review-evidence/、evidence-index.json。

source收集Head全部非docs/evidence文件（真实源码、配置、测试、合同、ADR、任务与交接），review-evidence收集`docs/evidence/<TaskId>/`全部已提交证据。其他历史证据原文不复制。源payload按SHA256去重，多个gitPath可映射同一个archivePath；导航应查manifest.sourceMembers，不能假设每个Git路径有独立成员。每条映射有gitPath/archivePath/blobOid/SHA256/sizeBytes。完整Head常规树先经git archive与ls-tree/blob校验，省略原文的历史证据也检查原始字节及禁止项。

evidence-index逐个历史及当前证据记录gitPath、commit、blobOid、SHA256、sizeBytes、所属任务testScope、archivePath或null、恢复命令/稳定仓库链接和保留策略。testScope是证据路径的所属任务范围，不把路径名称当真实测试PASS。代表样本可通过当前任务经审核引用/提交；本任务原证据全保留。省略原文必须能从明确Git对象恢复，Git访问不可用时不能声称这是完整离线审计归档。

git/diff-text.patch保留Base..Head全部文本差异，根据变更双侧原始blob判定文本集合，对其强制--text生成无binary编码的patch，防止attributes隐藏文本差异；git/changed-files.json含全部文本/二进制变更、增删/rename类型、前后路径与每侧blobOid/SHA256/size/mode。空侧为null。二进制标识按Git首8000字节NUL规则判断；已提交或本地gitattributes的-diff不能隐藏纯文本变更。被删/替换资产必须从受控Git对象恢复；不能从ZIP凭空恢复已省略二进制。变更两侧原始blob均做有限凭证扫描，不能以省略binary绕过被删秘密检测。

原始validation只保留在本任务映射位置，不另复制规范化JSON；未提供证据才生成review-evidence/validation.json明确NOT_RUN。实际规范化checks/ci在manifest，CI另见git/ci.json；运行时CI覆盖原始证据CI，不改写原提交字节。V2任何CI PASS/FAIL都要求commit=Head（包括总体PARTIAL），旧阶段CI不能复用为本轮CI。工具不主动查询GitHub，Master必须实际查询run和两个job，真实同Head事实再作为参数提供。

从已提交Head读取；脏树/未跟踪、非祖先、非commit、路径穿越、重复/大小写冲突、符号链接/submodule、禁止成员/机密、重算hash的payload或index伪造均拒绝。成员集合、源码blob、文本diff、binary/index JSON、原始validation与checks/ci重开后重算比较；V1也继续严格验证。有限扫描不等于全面防泄露。输出仍固定ignored artifacts/reviews，partial通过后原子发布，已有同名包拒绝覆盖；失败不替换最后有效包。

软门槛建议10MiB，超过15MiB须逐项记录大型内容必要性，不为缩包丢失关键实现/失败证据。Review ZIP不入Git，不上传第三方网盘。最终仅交一个compact ZIP；旧包先归档不可再生事实、核实恢复、再在新包独立校验后按白名单清理。详见[资源生命周期](resource-lifecycle.md)。

回归使用真实临时Git：保留V1原35正反例；新增V2默认、完整source/历史索引、增删改rename/大量截图、同Head实际大小比较、去重/篡改/CI/路径/符号链接/伪造hash和只读盘点副作用；本地Mac与现有LinuxCI运行，Windows专用脚本不改且原生未跑则NOT_RUN。

---

## V1 历史兼容合同（以下仅适用schemaVersion=1）

### 原合同

适用当前及后续已授权阶段。构包成功仅证明此工具执行的完整性检查成功，不表示任务、产品、CI或全面安全审计通过。Owner为工作项A；根verify和CI由Master接入。没有新增第三方依赖，仅使用PowerShell7、Git和.NET内置ZIP/散列API。

## 创建与重开

先提交全部交付内容，使工作树与未跟踪资料干净，然后使用完整40位小写提交SHA：

```powershell
pwsh -NoProfile -File scripts/create-review-package.ps1 -SchemaVersion 1 -BaseSha <完整Base提交SHA> -HeadSha <完整Head提交SHA> -TaskId G1-INFRA-001 -Status PARTIAL -EvidencePath docs/evidence/G1-INFRA-001/validation.json
pwsh -NoProfile -File scripts/create-review-package.ps1 -Root <仓库根目录> -VerifyOnly -PackagePath <ZIP绝对路径>
pwsh -NoProfile -File scripts/tests/ReviewPackage.Tests.ps1
```

Base/Head/TaskId/Status必须明确提供。Root默认脚本所在仓库；EvidencePath可省略，但验证项将明确NOT_RUN，CI为NOT_VERIFIED。EvidencePath必须精确对应Head中的已提交文件；绝不从当前磁盘读取未提交源码或命令证据。CI可用四个显式参数一起提供：`-CiRunId`、`-CiRunUrl`、`-CiCommit`、`-CiConclusion`（success/failure/cancelled/timed_out/action_required）。它们覆盖证据JSON中的ci，记录在manifest.runtimeCi及规范化validation中，用于避免已提交文档必须预知自身Head SHA的循环。未提供时保留证据JSON的ci或NOT_VERIFIED。Base必须为Head祖先，两者必须为commit本身，不接受分支表达式。分支记录为构包时当前工作树分支，快照提交以HeadSha为准，不要求当前检出恰好Head。完整差异固定Base至Head，不依赖origin/main。

输出固定为Git忽略的`artifacts/reviews/OntologyPlatform-Review-<TaskId>-<12位Head>.zip`。同名输出存在时拒绝覆盖。仅成功复检后才将同目录`.partial`原子重命名为ZIP；失败移除工具自己创建的partial，不删除已有交付。正常命令输出一条JSON，包含确切绝对路径、sizeBytes、sha256、taskStatus及真实verification结果；退出0仅表示构包/复检成功，退出1为拒绝或异常。ZIP不提交，不上传第三方网盘。

## 文件与完整性

- `REVIEW_SUMMARY.md`：中文范围、验证状态、阻断/未运行说明及当前关口停止要求。
- `manifest.json`：schemaVersion=1、taskId、完整baseSha/headSha、当前branch、UTC date、显式status、逐项checks、ci、Git命令/退出码、diffCheck、sourceMembers映射和excludedIgnoredPaths。
- `git/changed-files.txt`、`diff.patch`、`commits.txt`、`status.txt`、`diff-check.txt`：完整binary/full-index差异、提交详情、实测干净状态及diff-check退出码。所有Git调用固定color.ui=false，diff/log显式--no-color，避免用户彩色偏好污染机器可读内容；禁用外部diff/textconv，无改动时patch可为空，且Base/Head仍明确。
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

测试脚本建立临时Git仓库，提交真实Base/Head并调用实际CLI，验证正例、非祖先、脏树、未跟踪资料、禁止目录/文件、合成token、仅在被删patch中的token、ZIP篡改与路径注入，并在真实color.ui=always配置下提取patch，断言无ANSI、git apply --numstat退出0以及独立VerifyOnly通过。全部值为人工合成，不读取用户凭证。夹具清理仅限其生成且经绝对路径边界校验的系统临时目录。测试成功返回正常流程，失败throw；Master可用`& scripts/tests/ReviewPackage.Tests.ps1`接入verify和CI。必须保留实际测试数、命令和退出码，不把测试入口存在视作执行通过。
