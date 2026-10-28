# 组件容器后端漂移P2纠正

状态：IMPLEMENTED / PARTIAL，待独立复核及Master真实产品验收。保留原dc01601创建ID/标签回收实现和原审查P2事实，不重写已提交日志。

## 已复现问题

首次容器在daemon A成功创建后，外部改变默认Docker context为B，旧cleanup在B inspect(ID)得到准确no-such，虽A仍有容器却返回PASS。准确ID及label只在同一后端下才能解释absence。受控模拟A/B两个独立资源集合，旧实现真实RED：18tests中7失败（一个测试含context/info两个失败子分区）。没有切换实际全局context或真实创建/删除容器。

## 修正

首次创建前只读docker context show及有效docker info --format {{.ID}}，再用显式--context核对同EngineID，避免DOCKER_HOST与context指向不同daemon时静默换后端。context/EngineID严格有限非秘密格式、命令10秒预算，未知/权限失败拒绝创建。冻结的context+engineId入每条生命周期记录。

所有创建命令明确docker --context <冻结context> run，observe识别此准确prefix；wrapper后续Docker查询也带同context。每次创建前复验EngineID；cleanup inspect前后、rm前均显式context并复验EngineID。默认context变化仍能在原daemon验证并回收；原context对应EngineID变化/无法读取则不删除、不把其它daemon absence提升为PASS，最终exit1。回收仍只依据本次成功创建的准确ID和完整label/name集合。

## 验证

18tests最终PASS：包含A→B默认变化但原A正确回收、A引擎替换拒绝、首次/再次创建固定context与ID、context/info查询失败、DOCKER_HOST异源拒绝、清理期间查询失败；原创建碰撞/权限/错ID诊断/坏创建ID/foreign标签/rm无效及失败分区仍保留。五个实际main入口每个运行三分区（成功、inspect权限故障、产品命令成功后Engine替换），断言返回码、证据exit与对象保留一致。外部Docker/HTTP/dotnet为受控替身，不代表产品PASS。Python编译及diff-check exit0。

完整SelfTest再次实际运行，仍在该旧WEB树既存build.txt/build-final.txt CR/LF检查阻断，未改未授权证据。Master已有格式修正，集成后须重跑。此追加没有真实Docker变更、没有全局配置、依赖或权限变更。
