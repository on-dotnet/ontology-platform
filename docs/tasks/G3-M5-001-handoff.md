# G3-M5-001 进行中恢复入口

Master托管树 b389/ontology-platform，分支codex/g3-m5-master，Base e5b7e99715ee7ebfe419717f7cacf0c02dfcb78a。原main与六个DS_Store未动；只M5/E0，禁止G4/G5/Monaco/新依赖。

已冻结合同3e71049；E0 worker c0047d0/c8ca4b4已并入；WEB3e71bd0/843e27a、SEM90978ca/45cbb8d/666502b均已独立Review并并入。Master当前还在接入/验收，尚未main集成或交付。独立Review详master/independent-slice-reviews.md。

实测：用户确认自行开启能源选项，ACsleep0/display10；锁屏3分钟37心跳，官方CoreGraphics核外接睡眠60秒13心跳，均无Sleep。主有界monitor PID6932/session20595，最长12h，日志artifacts/g3-m5/host/session-continuity.jsonl；任务末精确SIGTERM该PID并取summary，禁止killall。不能预填完整会话PASS。

真实RIOT6PASS、真实PG+RIOT的M5 57PASS，均0skip；PG/容器精确finally回收见master/b1-*证据。实际DI正反2PASS；Web原267PASS/1生成快照漂移FAIL，已通过真实Kestrel两项OpenAPI导出新路由，下一步只补生成一致性/最终Web检查；新3截图浏览器尚未跑。Release构建0error，仅既有ASPIRE010警告。

P0 unit12、E0 timeline17+preflight11、G3真实控制流23、浏览器派发控制4、资源安全60、生命周期12等短门禁通过；新版ReviewPackage103已通过，正式SelfTest正在进行。历史M4 raw manifest无EOF换行，原字节未改；仅精确path/hash格式兼容，4正反限制例通过，JSON/秘密仍检查。

待办关键路径：完成SelfTest/实际AppHost前缀/Web→冻结Master接入独立Review→新M5 runtime最短API/UI Smoke→B1/B2获审main早集成→稳定源完整后端模块/7门禁全浏览器兼容→20能力/时间矩阵/权限/截图Schema→独立Review/提交/绑定→仅自身8卷准确白名单清理、worker原生归档→唯一V3/独立重开/回执并停等复审。正式ZIP尚未生成，CI/Windows/Intel/真实LLM均NOT_RUN，Monaco BLOCKED。

恢复工具/证据都在本树；.tools/pnpm/pythonlibs为同项目既有工具链接，Node24.22.1/pnpm11.28.8/SDK10.0.402准确。受锁离线store真实元数据指向g3-m3-master树.tools/pnpm-store（不是M4同名目录）。Docker已由本任务启动既有Desktop，29.9.2/linux aarch64；canonical镜像精确复用context-4fbf23514516632dcb651b5c05bf04e9992da52491607b6cf58de1f7348ff9ab，没有新history/image构建。最终保护旧G2/M4卷、所有私有runtime/PFX和未知活跃树。
