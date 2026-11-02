# 非作者独立Review记录

Reviewer：/root/postreview_reviewer（quality_reviewer，只读）。Master为唯一作者；本记录由Master按实际Reviewer消息归档，不冒充Reviewer写入或Master自审。

## 初轮及修订

Reviewer独立核对45个topo SHA、每提交diff-tree路径、90个授权/Review引用均与旧Head可解析内容一致；5项旧输入hash匹配；模拟11483对象/26树的before/after一致；Development18–19/54–55守卫和配置来源准确；当时两层diff-check0。独立执行9个只读host断言PASS（准确TaskId、4失败状态、越界/遍历/已存在输出、无效时长先拒绝）。该范围不包括产品重跑。

发现并闭合：①外联台账漏batch8两请求，现30条；②M2文档Bearer措辞可能隐含新wire枚举，改为NONE/API_KEY_REF与服务器注册固定header格式，不新增枚举。初轮无剩余P0/P1只表示研究候选可进入最终验证，不覆盖后来实际门禁。

## 最终验证新增P1（独立复现）

Reviewer确认旧host-monitor.json的44070字节、SHA256=6e425cb7ad191dd6a6fa8a2261a55d8599c2686ff4cb11d5c6d8bdd93a712122与d40 Git一致；整体JSON Extra data line2/char576，76行各合法。该文件由d40新增且不存在于旧Tested48be53e。verify.ps1:64–66拒绝，171–172在SelfTest套件之前退出；原SelfTest日志248字节hash a5983f894ace39f3f64ab62e6b8c11cf6d8aab0d42c9af9935b1ac677d9a5318匹配。

Reviewer亦独立复现任务树缺yaml；只读设置现有主树pythonlibs后21个YAML/TOML通过。环境故障定位不能覆盖SelfTest FAIL。结论：P1_MAIN_INTEGRATION_BLOCKED，赞成BLOCKED_WITH_WITNESS交付，旧49产品继承不变。当前不修改旧证据/共享工具。

Reviewer提出未来另批原字节JSONL改名+消费者/恢复索引，或必须旧路径时精确path+SHA兼容逐行验证；禁止宽泛豁免或仅改后缀逃过检查。Master在待批main申请选择后者作为最小候选，仍需明确批准。

## 尚待包外门禁

本轮真实SelfTest入口FAIL/套件NOT_RUN必须保持；封包仅验证BLOCKED证据可复核。最终提交绑定/唯一V3独立VerifyOnly结果由后续包外回执记录，不在本文件预填PASS。

## 最终precommit只读复审

Reviewer再次确认可封存BLOCKED_WITH_WITNESS证据包，无新增P0/P1；9PASS+1BLOCKED、SelfTest入口FAIL/套件NOT_RUN与原49继承分列正确，补救仅未来待批。独立核对当时34个变更/未跟踪路径均在owned范围，任务工具hash未变、本任务JSON合法，两层及未提交diff-check均exit0；独立执行test-review-evidence.ps1 -ExpectedHead b357fcb8a04b9b57c6f27cd3a10d530e3b556247 exit0（6checks/0screenshots，EVIDENCE_SCHEMA_ONLY）。后补的原始计时、远端复核和资源措辞更正已通知Reviewer。最终Head与唯一包重开仍由包外回执记录。

最终格式修正另经同Reviewer只读确认：Base到当前工作区及未提交diff-check均0；base64解码与f5985f2原日志逐字节相同（248字节、原SHA不变）；历史格式失败exit2独立复现。可追加修正提交；仅证据载体变化，产品/工具未变，BLOCKED结论不变。
