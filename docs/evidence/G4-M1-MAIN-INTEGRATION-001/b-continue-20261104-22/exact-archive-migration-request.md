# Run22 精确证据归档迁移申请

状态：PROPOSED_NOT_APPLIED；原文件仍在，未修改原始字节。

唯一阻断为 Run20 原始 MCP JSON 无末尾 LF，正式 SelfTest 在扫描阶段 exit1；27套、原生和产品检查未启动。不得修改正式扫描器或把本次失败提升为PASS。

申请仅迁移以下当前树路径：

- 原路径：`docs/evidence/G4-M1-MAIN-INTEGRATION-001/b-continue-20261104-20/agent-schema-result.json`
- 原始102104字节，SHA-256 `1fd721a4677ffe0d589609d96ac4db9f75a1bd8bdc811ae8c92843b2641ea51a`。
- 无损载体：本目录 `proposed-agent-schema-archive.json`，SHA-256 `644095d7dcbc2feaaae474cade964f4426562bf86dc027052091a8dd66aa471b`；读取其 `utf8` 字段后 UTF-8 编码可恢复原字节。
- 批准后：先复核并提交载体，再从当前树删除上述唯一原路径，新增已执行迁移回执；载体本身保留提案时状态，执行事实另记。保留原 ignored 输出、原 Git blob、全部历史提交和SHA。旧路径引用由该映射或原提交 `9d865b1335f6b396759533984801405726a0f399` 精确恢复。
- 不改变产品、正式测试、共享扫描器或旧任务证据，不修改 main；新T重新执行完整验收。

该迁移不会丢失原始内容，但会改变当前树中旧路径的直接可读性，因此需要明确批准。自动审批审查已拒绝未经明确迁移授权的删除操作；该命令未执行。
