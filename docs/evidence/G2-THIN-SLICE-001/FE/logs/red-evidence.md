# FE实际RED观察

以下为本会话实际运行输出的摘录转录；首轮原始stdout未写文件，不伪称完整原始日志。

1. 首个14测试的3套件：`Cannot find module './g2-client'` / `./draft-state` / `./event-stream`，3 suites failed。实现后14/14 green。
2. payload缺字段：`SSE解码 > 已知eventType但载荷缺字段也拒绝`，`AssertionError: promise resolved "undefined" instead of rejecting`，1 failed / 6 passed。加强判别验证后green。
3. 结构新增Class浏览器：`locator.selectOption: Test timeout of 30000ms exceeded`，等待`combobox 结构操作`；当时仅存在旧三元组替换。新增表单后通过同一测试。
4. dirty内部导航浏览器：等待`button 丢弃未保存修改`超时；增加明确丢弃和内部导航保留后同一测试通过。
5. 首轮6浏览器：4通过，2条`getByRole('alert') resolved to 2 elements`，Next内置`__next-route-announcer__`与业务alert冲突。限定组件alert后同一行为断言通过。
6. 首轮lint：`react-hooks/purity Cannot call impure function during render`，指向审核render中的Date.now。改为可清理时钟状态后lint0。
7. 首轮verify SelfTest：`structured-syntax FAIL YAML/TOML解析失败或项目解析器不可用`。复用已批准Master隔离parser环境后SelfTest0；没有改机器Python或依赖版本。
8. 默认Active查询：浏览器真实请求断言RED，预期`releaseId:null`，实际`releaseId:"release-ui"`。修正为Active当次由服务器解析快照、历史版本显式ID后，同一测试GREEN。
