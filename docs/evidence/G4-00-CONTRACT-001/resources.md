# G4-00 资源与恢复

TaskId=G4-00-CONTRACT-001，RunId=g4-contract-local。创建即登记：托管树/分支由本任务唯一写入，Base=d1a61daffe844475b07705797e3ad325cc3f2945；git worktree list准确对象见worktrees-retained.txt。开始20棵树（主树+19附属），本任务新增1棵共21棵；其他20棵KEEP，理由为本轮仅G4合同归档且旧G3/G6树/私有恢复不属删除范围，解除条件由原owner确认关闭并通过生命周期门禁。本树未合main，KEEP至ChatGPT复审关闭且另有集成/归档授权。

原main六个.DS_Store不动。用户Downloads输入ZIP保留。原始输入24文件/283725 bytes已归档本任务Evidence/input-v1.1，可从最终Head恢复。临时重复解包目录/private/tmp/G4-00-CONTRACT-001-input-v1.1为精确清理候选，须独立Review、对比逐文件SHA、nofollow保护，真实Apply回执另存。

任务隔离/private/tmp/g4-00-validation-venv与安装元数据用于本轮独立复验，KEEP至复审关闭/重放入口确认；无global PATH/依赖修改。精确依赖来源、版本、license、artifact hash见validation-dependencies.json。临时/private/tmp/g4-*.py为本轮生成辅助命令，KEEP至交付确认，不能泛删同前缀历史文件。重跑实际验证使用Evidence/check-bindings.py、check-review-cases.py与input-v1.1/verify_input.py、verify_schema.py；venv只承载工具，不入Git/ZIP。

artifacts/g4-00为SelfTest原始输出/计时；artifacts/reviews只允许最终一个本任务V3。所有ignored仅聚合索引，凭证/缓存不打包；正式结果摘录进Evidence。

Docker新建/启动/删除命令数=0；Docker before/after数量、旧开发环境health=NOT_RUN（没有访问socket），不声明Docker PASS或物理回收。系统/全局/其他项目无清理。项目产品源码全未变，开发环境保留证据限Git对象/既有树存在，真实运行健康NOT_RUN。

实际Apply已完成：独立Reviewer获审inventory精确匹配，24文件/283725逻辑字节→0，准确目录不存在。见cleanup-receipt.json；物理回收NOT_VERIFIED。任务21树保留，Docker未访问、未启动。
