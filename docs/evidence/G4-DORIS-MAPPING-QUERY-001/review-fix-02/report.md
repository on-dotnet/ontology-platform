# RF-02｜E1 执行身份资格

本批 Base 为 `a363fbd53d3f2813539534f921f2b21004638eec`。产品二进制输入仍是 `9780c8f91cd084c1df11c604186d22d7f08f3023`，上一轮工程实测是 `544c134f2db913a5392605f53726ae67e7c4d72e`。本轮五次短执行绑定 `f2673f2c62537b5422f308b99cfb25da464eee35`。

旧消费者对真实原件返回 PASS/316。本地完整 Git 仓库的执行轨迹确认 E1 分支未读取命令 inputFingerprint。原复审对两份失配原件也得到 PASS/316，同类 E2 失配被拒。两份失配放行是委托方提供的原复审观察；本轮独立旧版运行使用原始未改动证据。[本地旧版见证](s1/index.json)

| E1 选定场景 | 执行 | 真实结果 | 命令原件 |
|---|---|---|---|
| 原合成授权过期 | FRESH | exit 1，grant_expired_or_missing | [0266359b](originals/0266359b2ff94dda9baf8ba8b7c22f4c-receipt.json) |
| 120 秒 TTL | FRESH | exit 1，grant_ttl | [181c11aa](originals/181c11aa9bb8473e9750e1f1b733556e-receipt.json) |
| 旧目录 | FRESH | exit 1，catalog | [dca87ab5](originals/dca87ab5ab3e404a88c60b022e46a739-receipt.json) |
| 旧激活 | FRESH | exit 1，activation | [8024acbd](originals/8024acbdf1db41a699a21ebf0c66ccdd-receipt.json) |
| 健康前态 | FRESH | exit 0，PREREQUISITES_ONLY；四主体、18 字段、180 秒门槛 | [fcb1fc4c](originals/fcb1fc4cc74e427eb71dd262b9ed705b-receipt.json) · [会话探针](originals/2cf5db0984d341b8b5a624a61b887733-receipt.json) |

正式资格核对五份浏览器命令、双流、宿主 START／READY／END、argv、真实 API 构建、十二个驱动的完整指纹、场景参数、输入稳定与审计窗口。四次拒绝均发生在 scenario_ready。健康场景的 MTP 票据探针在 20 秒预算内实际通过 1/1，资格入口核其精确 filter、argv、AgentTests 构建指纹与浏览器时序。五个场景选择的 58 份原件全部参与核验。过期和短 TTL 各只临时调整已有 execute 授权一行，审计后按原时间和整行散列恢复。[选定输入及原件](selected.json)

同一 FE 审计 inode 219380 扫描 20,480,189 字节。四次拒绝均为零审计行，健康窗口有 8 行，五个窗口均零源表变更、零固定业务 SELECT。原压力正对照按同解析器、inode、偏移和散列复核，保留 790 行、154 次变更、173 次固定业务读取。首轮扫描因末条命令后的日志尚未落盘退出 1，确认覆盖边界后以同命令身份短定位成功。[新审计命令](originals/2c1629a0435a48098bea95ab16697abc-receipt.json) · [失败与资源后态](resource-and-diagnostics.json)

## 历史复用与影响

- 最早两份旧拒绝缺少可重建的完整驱动。其后两份旧目录／激活未将差异参数纳入指纹，再后两份绑定较早的准入实现。这六份记录均固守旧 Base 的身份。最新旧健康有可恢复的执行输入；本轮选定新执行，使五个短场景共用同一驱动及审计窗口规则。
- RF-01、AC06、PG、E2 和 E3 沿原准确执行身份重新核资格。backend、apps/web 和全部依赖锁无代码变更。Python 与 Node 的证据运行目录校验、S1 快照及会话探针输出共涉及 3 个登记驱动，其余 9 个驱动逐字节一致。旧运行的完整有效逻辑与原驱动逐一比较，新 E1 按全部 12 个当前文件重新计算指纹。已编译票据探针使用 Owner 的独占临时会话文件，完成后移入本批目录。
- 五次验证只读现有两表。实体 1 行、目标 3 行，原行散列核对一致。三次零在途后，FE、BE、平台 PG 已回到 STOPPED_KEEP，旧 14 个 ID 已退出，三个易失服务按原 ID 运行。平台 PG 容器退出 0、原生日志确认干净关库，exec 通道退出 137。
- 早期生产精测为 7,275,376 字节。历史 C# 整文件格式检查的基线与候选均 exit 2，271 条继承诊断，原本新增 0 条。本次 C# 变更行数为 0。CI 与其他平台 NOT_RUN；G4 总体 PARTIAL。
