# 两个本任务托管worker树归档前核查

2026-10-27T16:10Z；SEM/WEB Owner只读实查并报告。尚未archive；需独立Review、同HeadCI成功后才执行。Master及所有旧树/原6个DS_Store保护。

SEM准确路径/branch见任务卡，Head8be4574bb1c715e017e7e0922b98a76b51eecd17。git status非ignored为空；owned_paths对Master dfce2df diff为空，末两提交git cherry均'-'。ignored830项55269038逻辑字节（.tools1链接、artifacts20文件91231字节、backend805文件55142612字节、scripts4pycache35195字节）；无独立私有runtime/PFX路径。pythonlibs链接目标在原主树，不跟随。进程参数/cwd核查无持久引用；Docker0容器/0树mount引用。

WEB准确路径/branch见任务卡，Head1c98e05717cb7e3f311ba41b7b07f093aa64dc40。git status为空；ontology源码+WEB证据对Master dfce2df diff为空。ignored7折叠路径533191697逻辑字节、610422784名义分配字节；node_modules486744678，apps/web/node_modules32771，.next45933472，tsbuildinfo404043，artifacts41538（19文件），pycache35195，.tools只有1链接。未发现独立私有runtime/PFX路径，无持久进程/Docker引用。

Master在删除前准确复制SEM artifacts/sem-m2及fuseki-builds、WEB artifacts/G3-M2-WEB至自身ignored worker-archives：39文件132769字节，源/目标逐文件size/SHA256一致，清单worker-raw-archive.json。保留独有原始终端失败日志；不复制依赖/构建缓存，不跟随链接、不读取私有runtime。其余缓存由锁定restore/build再生。名义/APFS共享容量不当作物理回收字节。

原生archive_worktree将保存可恢复Git快照再移除checkout；不是删除历史分支。两个任务refs保留待人类复审，解除条件为复审结束且无跨机器引用。最终状态以后置归档/同HeadCI/独立实查回执为准。
