# M5 isolated Synthetic runtime closed

G3-M5-001 / g3-m5-7d512550ef69 / CLOSED / Synthetic 可再生。

真实适用本地验收已结束：M1–M4原链600项PASS，最新定向M5浏览器202fd26ff8bb4362914bb81a98623fdc exit0/50项PASS；固定发布版本读取通过。其余六门禁分别exit0，原整链及两次后续观测失败如实保留；不宣称一次七门禁命令exit0。最终组合见master/final/browser-composite.json，兼容/G1见master/remaining-six，观测/trace/故障/性能见master/bounded-four。每次launcher finally均关闭；执行前仍须确认准确卷0容器引用。

仅本任务合成验收数据，无生产或用户业务数据，原始源码/合成语料/实际报告均已提交，可按scripts/acceptance入口和原有已批依赖重建。精确八卷允许在独立审查、提交、当前Backend/metadata/0refs/24h重验后实际回收：

- `g3-m5-7d512550ef69-alloy-data`
- `g3-m5-7d512550ef69-fuseki-data`
- `g3-m5-7d512550ef69-grafana-data`
- `g3-m5-7d512550ef69-loki-data`
- `g3-m5-7d512550ef69-postgres-data`
- `g3-m5-7d512550ef69-prometheus-data`
- `g3-m5-7d512550ef69-rustfs-data`
- `g3-m5-7d512550ef69-tempo-data`

旧G2八卷、其它任务树、共享canonical镜像/history、Master与worker私有runtime/PFX/realm/依赖缓存及保留reader均保护；不全局prune/restart/改DB。物理实际回收字节UNKNOWN，不以rm0或列表缺席冒充删除。当前Master保持以便ChatGPT复审；不启动G4/G5。
