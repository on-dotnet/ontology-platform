# 整分支独立审查（原始发现）

Reviewer m1_contract_review（非作者，Astra/high），d6aab6b47e63c9d5deadfa480f6659c62c5ed138..02763a1144f25d30cdac42c907859a8784226f49。Reviewer确认单文件diff与git diff -U10一致。

结论 Spec FAIL / Quality FAIL，C0/I4/M1，当前不可合并。已核对第三轮完整实测及原始hash、SEM96/PUB55/QRY49/Agent33零跳过、126成员reader/实际V2；后端发布资格、Legacy兼容及有界同构未发现新增阻断项。没有新直接依赖或M2–M5实现。

## 统一修复列表

1. I1（source-editor.tsx:71、workspace.tsx:255）：异步file.arrayBuffer完成后调用旧工作区回调，整个旧state替换可覆盖期间新名称/其他源或切换后的草稿。Reviewer用实际TSX处理器、实际回调及延迟Promise在内存复现。须函数式更新当前state，并绑定草稿身份/修订及导入代次，拒绝失效/丢弃/切换/后发操作后的旧完成。补延迟/乱序负例。
2. I2（g3-m1-browser.mjs:98/105、workspace.tsx:278）：dirty时断言保存enabled早于填写必填reason，新页面此时按钮始终禁用。提前填理由，独立断言dirty标记；保留异步完成等待、改变字节导出与原字节重入。目前补测在更早429退出，无实际GREEN。
3. I3（g3-acceptance-runtime.py:24/36–42）：固定证据目录跨轮混合。最新full-g2-e2e为429 FAIL，未执行的M1文件仍是上轮PASS38。每次全新/拒绝复用目录，runId/sourceHead/runtime身份及逐步骤状态；仅消费本轮输入，后续NOT_RUN；保留历史成功和失败。
4. I4（g2-full-chain.mjs:13–18/160–161）：激活后只读query真实429。生产JenaSemanticRuntime.cs:227即时并发槽背压有效，不是固定时间窗限速。验收仅对准确semantic_busy的只读query作有界等待/重试，完整记录每次状态/等待/耗时；不重试写命令、不放宽生产预算，其他错/耗尽仍FAIL。重跑增强浏览器与统一入口。
5. M1（G3BoundaryTests.cs:19–20/58–59/34）：相邻成员空行、循环变量声明处中文用途说明按backend/AGENTS补齐，不改行为。

## Declined to judge 与执行边界

- 私有真实G2备份/升级前Run/Event库导入：证据是实际服务上的历史协议夹具，不能外推生产迁移演练。
- coverage表未逐字段动态变异组合：生产检查已审，但不声称每个组合实测。
- 精确SHACL行列：当前bundle/hash及null行列，未实现精确定位。
- 最终CI/main/资源/ZIP：后置门禁；Reviewer独立访问6a CI网络不可达，未把Owner陈述升级为独立核验。
- 真实LLM/生产HA/WindowsIntel/完整供应链/M2–M5：不在本次授权证明范围。

Master接受上述边界；最终CI仍由实际gh run和两个job核验。统一一轮fix wave，随后仅一次限定复审，不预填未来PASS。
