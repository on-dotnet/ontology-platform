# 下一单项执行授权草案（当前不可执行）

现状BLOCKED_WITH_WITNESS / RESOLVER_TOOL_APPROVAL_REQUIRED。最小实际请求：**只批准既有pip26.2.2在一次性任务目录进行两平台binary-only dry-run依赖求解时，有界读取官方wheel/metadata payload，不安装任何目标包**。这是对本轮“零wheel下载”的明确变更，必须等人类新批准；本任务不会执行。pip本机来源、源码SHA、MIT许可证及vendored解析器信息见tool-inspection.source.json。

只准pypi.org和files.pythonhosted.org HTTPS，拒绝redirect至其它域、userinfo/query/fragment及非白名单URL；固化当时官方索引/文件URL/SHA/size后才取payload。每文件最多64MiB、累计512MiB、最多200响应、最长60min、目录预算2GiB；未知大小或超限立即停止。精确TaskId/RunId记账，Master唯一持有临时目录。网络计量及host/path/响应限制必须由执行层fail-closed实施，不能仅凭pip参数声称已生效。

输入仅当前Docling Lite四extras；禁止standard/all/models-local/Paddle/模型权重/OCI/sdist/PEP517/编译/API/安装/系统修改；使用--isolated、--ignore-installed、--only-binary=:all:、--dry-run、--report，不把宿主已装包混入结果。patch/相同glibc基础系列必须有官方支持证据并冻结；不能用3.12.0代替未知patch。pip跨平台marker仍须独立目标环境复核，不将--platform理解为全部marker已跨平台。工具源码哈希改变、CPU轮廓无法保持、未知费用或容量直接阻断。未列完整依赖payload清单前不能自动下载；下一执行应先产生精确allowlist再由已获范围内的下载器验证预算，不修改本轮代码来绕过限制。

关闭：只删除该新Run精确可再生目录及日志副本，先保留解集/hash/NOT_RUN证据、非作者Review和任务提交；不动当前树、PREP、旧Docker、系统pip/cache。审批只覆盖这个求解实验，不包含解析器运行或后续容器PoC。审批未到或无法实施计量/marker保证时继续BLOCKED，不反复预检。

## 按合同登记的新工具候选附件（不同时申请安装）

uv==0.9.7，来源https://pypi.org/pypi/uv/0.9.7/json；Mac ARM64工具载体uv-0.9.7-py3-none-macosx_11_0_arm64.whl，声明size=18345022，SHA256=0fdbfad5b367e7a3968264af6da5bbfffd4944a90319042f166e8df1a2d9de09。准确下载URL见本任务resolver-candidate-metadata.json，当前未取payload。声明许可字段为null，源码许可证尚未取证，license=UNKNOWN；零payload求解能力=CAPABILITY_NOT_VERIFIED；不是可执行安装批准清单，不能声称新工具即可解除阻断。

如未来另选此工具，必须先独立确认精确tag源码LICENSE/NOTICE与零payload能力，单独批准在本Task工具隔离目录下载/安装/核验，登记归属和删除计划，不改机器PATH/全局环境。由于已有pip可在新增payload权限下求解，当前不捆绑申请uv下载。上述文件大小/hash只是registry声明，不是本地实测。
