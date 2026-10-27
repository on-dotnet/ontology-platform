# 完整浏览器首关定位与独立修复审查

首次完整入口exit1；pipeline-90fbe65088824476984352c4029dabfa前12stage PASS，runtime第一关full-g2-e2e 31项PASS后TimeoutError，phase=real_ui_source_import；后六关NOT_RUN。原pipeline/acceptance/failure完整保留，不能改写PASS。最后两项实际创建/四源scope精确保真均PASS。

根因：workspace默认centerView=source，SemanticGraph仅graph时挂载；旧验收器下一句却直接等待RDF结构投影标题。M2 UI必须显式切换视图，产品行为符合已授权图/源码切换。

Master仅修公共验收器g2-live-browser：点击图视图→原heading等待→canvas等待/可见断言→点击源码视图，随后原精确结构、CAS、本地文本保留、导出、审批发布/查询/Run/SSE/回滚与M1/M2断言全部保留。无产品代码/超时/预算改动。

Reviewer=/root/final_review独立核实根因，C0/I0/M0，独立node --check与目标git diff --check均exit0；认可仅重跑受影响的完整七runtime gates，禁止把原pipeline改为PASS。修复后实际运行结果以后置验收JSON为准。
