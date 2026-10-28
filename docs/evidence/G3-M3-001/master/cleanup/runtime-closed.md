# G3-M3-001 Synthetic runtime CLOSED

仅关闭本轮准确可再生Synthetic验收环境，不表示ChatGPT已批准M3阶段。651ff9e continuation resume-aa5a1647d6f54c1580191ce4bfabdf37实际PASS，前五关同输入复用并保留原FAIL；400业务+8真实依赖故障、27样本性能，launcherStopped=true/exit0。以下卷无用户/生产数据，测试源码/fixtures、实际证据与重建入口已提交。

- g3-m3-daa8b53191e9-alloy-data：CLOSED / Synthetic / 可再生。
- g3-m3-daa8b53191e9-fuseki-data：CLOSED / Synthetic / 可再生。
- g3-m3-daa8b53191e9-grafana-data：CLOSED / Synthetic / 可再生。
- g3-m3-daa8b53191e9-loki-data：CLOSED / Synthetic / 可再生。
- g3-m3-daa8b53191e9-postgres-data：CLOSED / Synthetic / 可再生。
- g3-m3-daa8b53191e9-prometheus-data：CLOSED / Synthetic / 可再生。
- g3-m3-daa8b53191e9-rustfs-data：CLOSED / Synthetic / 可再生。
- g3-m3-daa8b53191e9-tempo-data：CLOSED / Synthetic / 可再生。

保护旧G2八卷、daily M2与current canonical镜像、唯一新history、所有其它项目；不清私有runtime/PFX。恢复使用g3-runtime.py prepare --milestone M3生成新私有环境，再由g3-acceptance-runtime.py --start-runtime完成bootstrap，不直接复用本轮已关闭数据库的旧realmFile。
