# G4-M1 恢复任务防重复踩坑台账

| 编号 | 已发生/确定的风险 | 下轮硬性机制 |
|---|---|---|
| L01 | 完整许可证据先于镜像层下载导致循环阻断 | A来源/B镜像取证/C正式商用分层门禁；用户审批后才变更 |
| L02 | 遗漏Keycloak/ASP.NET精确OS/JDK许可材料 | 逐 digest 本地SBOM，未覆盖独立列NOASSERTION/待法务，不伪证 |
| L03 | 重复45秒超时的远程SBOM查询 | 已存在同SHA证据先复用；依旧无法远端查全则直接转已批准本地层取证 |
| L04 | 先拉全双架构消耗磁盘/网络 | 仅本机 ARM64 必需4镜像；AMD64远程manifest观察，Windows后续实测 |
| L05 | 首次执行错误 `dotnet test --filter-class` 返回零测试 | 命令先 `--help`；需检查 actual count >0 / failure exit；固定日志 |
| L06 | 试图同步写公共OpenAPI生成文件导致拒绝 | Master single writer/生成链唯一；Worker只写独占目录 |
| L07 | UI sessionStorage 曾缓存带userinfo/token的URL | 保留已有修复，真实浏览器/刷新/URL及负例审计，不记录凭据 |
| L08 | 连接Probe并发、幂等、审计和ETag被 Reviewer查出缺陷 | 复用修复后源码，真实PG事务/CAS并发/故障注入逐项验收 |
| L09 | 仅ContentLength不足以限制流式请求实体大小 | 真实读取64KiB上限+chunked/HTTP2负例，在业务端点之前拒绝 |
| L10 | `docker image ls` 前后输出参数不同造成假漂移 | 固定相同命令/daemon/context/digest/ID，独立After再检查 |
| L11 | 根路径/参数误用导致零进度 | 先查仓库当前CLI帮助、存在路径/准确SDK，再执行受影响层 |
| L12 | 迁移remove误用 `--offline` | EF CLI先核验当前帮助；未应用的新迁移安全处理与提交证据 |
| L13 | 未完成的Compose消费者被“仅有源文件”假通过 | runtime preflight 必须能实际调起合成PG/OIDC/API/UI；失败保留BLOCKED |
| L14 | Docker旧G3/G6共享卷/镜像容易误删 | 逐资源TaskId/RunId/标签/ID/引用；只删独占、不运行全局prune |
| L15 | 产品49项未运行不能用15+21+73组件测试顶替 | 独立列组件/真实产品/跨平台/安全/许可验收状态 |
| L16 | 多Agent争公共源码/长期工作树膨胀 | 以现有M1 Head恢复，新树仅需的Worker；非作者Reviewer，及时提交受影响小切片 |
| L17 | 临时脚本/无来源工具潜在自动下载 | 复用平台已装CLI，缺工具提明确范围；禁止`curl | sh`及自动安装 |
| L18 | 文档质量不等于可下载可执行成果 | 一个ZIP、SHA256、源版本/Manifest，最短启动词和用户授权分明 |
