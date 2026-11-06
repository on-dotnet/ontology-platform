# Run37 产品 P1：两文件写入范围申请

状态：`WAITING_FOR_EXACT_TWO_FILE_PRODUCT_WRITE_APPROVAL`。本文件不是批准记录。

- 当前测试提交 T37：`79d1d42f43e8e7da23e905da18a374037b6b22a3`。
- Run37 的 I01–I06（含 I01/I03 后置闭合）已获独立 PASS；I07 保持原 `BLOCKED_WITH_WITNESS`，I08 未执行。
- 原始失败、短诊断、失败准备记录、Git blob 与恢复映射均保留；不改写成 PASS。
- 15MiB 硬上限保持，未更新 main、未进入 M2，未创建新的最终 V3。

## 已证实的问题与结论边界

初始目录读取尚未结束时，发现按钮仍可点击。若真实目录返回 `403 catalog_access_forbidden`，组件递增与发现操作共用的代际；稍后已成功创建任务的 202 被当作旧响应丢弃，任务没有写入 job URL，也没有保留恢复入口。

原正式 Run37 的对应作业在约350ms内达到 `PARTIAL / catalog_permission_limited`，但浏览器等待超时。原报告没有记录完整响应先后顺序，因此不宣称已还原原失败的精确事件序列。

实际组件的三种 Promise 调度和一次真实浏览器确定调度已证明该产品竞态可达：真实403→连接重验200→原字节202→15秒无job URL。自然短诊断中，403/重验先完成再发现则成功，记录同样保留。确定调度仅延迟准确两条真实响应，不替换状态或正文；源ACL实际 `true→false→true`，恢复与执行输入获非作者复核。

## 请求新增的唯一产品写入范围

1. `apps/web/src/features/connections/catalog.tsx`
2. `apps/web/src/features/connections/connections.test.ts`

拟在现有任务工作树及分支继续，由 Master 单写者应用此精确补丁。补丁仅给目录/任务读取建立准确owner互锁，读取与源403重验未完成时不发送新操作；保留原代际、AbortSignal、授权拒绝及父子操作所有权保护。轮询仍能在取消待响应时撤权，不宣称双向串行化。

补丁原件保留于本任务 ignored `product-proposal/two-file-product-fix.patch`；Git内使用 `two-file-product-fix.archive.json` 的UTF8字段无损保存，原标准patch的空白上下文行不直接作为证据文本路径提交。恢复时按UTF8编码并核对下列SHA，补丁字节不变。SHA-256：
`4a9735481c2dfeae38dae68a0924d18695c74ada247d7cd8f2d175ea2f3c3293`

候选文件SHA-256：
- catalog.tsx：`c848454e65ace628e0ee4af1290e50d4868447ed4dd7f9608eb628a130893f5b`
- connections.test.ts：`87712479050b9d2e575df345fb83e9a8a2f69778ab328705ec75917b9de126a8`

无 REST/DTO/数据库/依赖/锁文件变化，无增加浏览器等待来掩盖缺陷。

## 已完成的隔离验证

- 新增初读/双读互锁4例，在原产品源码上实际RED。
- 精确候选替换的完整Web组件测试：23文件、385测试、零失败。
- TypeScript compiler host只替换准确两个候选文件：零类型错误；原路径lintText零错误/警告。
- 原有不再可达的“初始读pending时发命令”测试改为正常初读完成后的真实可达轮询401/403、取消503晚于源403及发现后卸载交错；继续严格核对旧状态不恢复、提示不覆盖及owner仅释放一次。父子互锁等既有断言保持。
- `git apply --check --whitespace=error`通过；非作者限定源码/测试Review通过。

这些是未应用候选的隔离验证，不是新稳定T的完整验收，也不提升原I07。

## 授权原因与后续

原计划第2节的精确 owned_paths 不包含这两个产品文件，并要求发现必要范围外修改时“单独提交位置、影响、负例和授权差异；对应门禁停止”。用户此前仅解除三文件限制，没有授予本次产品路径写入。因此当前只保存补丁和证据，没有写入现行产品。

如批准这两个文件及上述精确补丁，将在现有任务分支应用、复核并冻结新T，重新完成适用完整验收、独立Review、15MiB内唯一V3、独立重开及包外回执。main更新和M2仍需另行明确批准。
