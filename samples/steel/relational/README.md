# 冶金样例库

这是人工合成的热轧生产数据，覆盖两个厂区，可用于演示按本体追溯从炉次到钢卷的生产记录。

| 本体对象 | `mes` 模式中的表 | 到下一工序的关系 |
|---|---|---|
| 炉次 | `heat` | 通过炉次的 `cast_no` 找到对应浇次 |
| 浇次 | `casting_sequence` | 通过板坯的 `cast_no` 找到产出的板坯 |
| 板坯 | `slab` | 通过 `slab_rolling` 找到参与的轧制事件 |
| 轧制事件 | `rolling_event` | 通过钢卷的 `rolling_id` 找到产出的钢卷 |
| 钢卷 | `coil` | 生产链终点 |

五个对象都用业务主键、`org_id`、`site_id` 表示外部编号、组织和厂区。板坯和钢卷的 `weight_t` 以吨计。完整的 IRI 和连接方向见 [expected-bindings.toml](expected-bindings.toml)。

样例按作业批次记录轧制事件。同一批次可以处理多块板坯，个别板坯在前一批次开始粗轧，在后一批次完成卷取。每卷钢仍对应一块来源板坯，两者编号只有首字母不同。质量检验和表面缺陷分别记录在 `quality_inspection` 和 `surface_defect` 中，视图 `v_coil_quality` 按卷汇总检验次数、合格次数和最近检验日期。

在仓库根目录运行 `./dev.ps1 seed-steel`，即可将样例装入开发用 PostgreSQL 的 `steel_mes` 库。只读账号为 `steel_reader`。账号口令和新建数据源的参数见[开发手册的“冶金样例库”一节](../../../docs/development.md)。

测试镜像使用 [backend/tests/fixtures/connectors/steel/](../../../backend/tests/fixtures/connectors/steel/) 下的副本：两个 SQL 文件和 `expected-bindings.toml`。修改这三个文件时须同步更新，两处文件必须逐字节相同，`./dev.ps1 seed-steel` 装载前会比对。
