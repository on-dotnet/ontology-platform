# 实际测试矩阵及失败保留

| 范围 | 证据和数量 | 适用结论 |
| --- | --- | --- |
| Parser合同实现 | 35 unittest，9 seed/18 spans | 真实macOS ARM64 Python标准库，含UTF8/BOM/CRLF/中文/emoji/CSV双引号/多段/坏编码/版本/范围/hash篡改 |
| 文件安全与资源 | Parser组内真实权限拒绝、FIFO、root/祖先symlink、替换竞态、增长budget+1、fd关闭；每轮11临时目录清理并断言不存在 | PASS仅本机安全边界；Windows不支持时fail closed |
| Provider/费用/Secret/Compose/清理 | 30 unittest | 内存模拟，不是网络/计费/容器成功 |
| 元数据图审计 | 3 unittest | 缺节点/extra和pin冲突检测；不证明版本可解 |
| G6前置门禁 | 4 unittest；原始24输入逐hash | 真实坏import、零发现、_FailedTest、manifest删除拒绝；2个准确临时目录实际回收 |
| 独立附加攻击 | Reviewer 24随机CSV/1137codepoints/4篡改；平台13项 | 非作者独立结果，见independent-review.md |
| 供应链 | 162节点/334声明/3493artifact记录/4模型repo元数据 | 枚举及内部一致性；安装闭包BLOCKED |
| 工程门禁 | verify静态/SelfTest/最终diff-check/test-review-evidence | 原始日志和真实exit保存；不代表产品 |
| 真实Docling/PaddleOCR/Compose/Provider/Secret store | 0调用/0安装/0镜像和权重下载 | NOT_RUN，明确禁止 |
| .NET/Web/浏览器/Windows/Linux | 本轮无此实现 | NOT_RUN，不为PREP强跑无关整栈 |
| Actions | 未触发 | NOT_RUN，采用LOCAL证据 |

初始负例：Worker缺实现/占位导入、首实现6FAIL+1ERROR原字节见tests/*.source.json；随后修复35PASS。Master平台缺模块红例见platform-red.txt；26绿例后非作者发现5项真实缺陷，修复后30PASS，不能删除初审失败。最终辅助入口曾接受_FailedTest，非作者发现后收紧并补4负例。

SelfTest第一次计时器fingerprint错误exit2，SelfTest没运行；第二次clean worktree缺现有YAML工具路径exit1；仅连接原仓库已存在.tools/pythonlibs后完整PASS，无依赖安装。timeline schema2区分exitCode与timingStatus。后续最终提交绑定验收日志覆盖实际新输入，保留先前日志。

只读资源After初次比较dict排序TypeError/exit1；修正后成功，原Before history字段错误保留NOT_VERIFIED；从不据此声称删除。元数据大响应超过4MiB拒绝，改精确release接口并继续固定点，失败类别保留。独立随机CSV生成器BOM期望错误、未采集180份结果也明确保留，不计PASS。
