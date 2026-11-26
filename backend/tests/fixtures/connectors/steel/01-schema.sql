CREATE SCHEMA mes;

CREATE TYPE mes.coil_status AS ENUM ('produced', 'inspected', 'shipped', 'on_hold');

CREATE TABLE mes.casting_sequence (
    cast_no character varying(16) PRIMARY KEY,
    org_id character varying(12) NOT NULL,
    site_id character varying(8) NOT NULL,
    started_at timestamp with time zone NOT NULL,
    superheat_c smallint NOT NULL,
    casting_speed_m_min double precision NOT NULL
);

COMMENT ON TABLE mes.casting_sequence IS '浇次，记录连铸机一次连续浇铸的生产过程';
COMMENT ON COLUMN mes.casting_sequence.cast_no IS '浇次号';
COMMENT ON COLUMN mes.casting_sequence.org_id IS '组织编号';
COMMENT ON COLUMN mes.casting_sequence.site_id IS '厂区编号';
COMMENT ON COLUMN mes.casting_sequence.started_at IS '连铸开浇时间，含时区';
COMMENT ON COLUMN mes.casting_sequence.superheat_c IS '中间包钢水过热度，单位为摄氏度';
COMMENT ON COLUMN mes.casting_sequence.casting_speed_m_min IS '浇次平均拉速，单位为米每分钟';

CREATE TABLE mes.heat (
    heat_no character varying(16) PRIMARY KEY,
    cast_no character varying(16) NOT NULL,
    org_id character varying(12) NOT NULL,
    site_id character varying(8) NOT NULL,
    steel_grade character varying(12) NOT NULL,
    tap_temp_c smallint,
    c_pct numeric(5,3) NOT NULL,
    si_pct numeric(5,3) NOT NULL,
    mn_pct numeric(5,3) NOT NULL,
    p_pct numeric(5,3) NOT NULL,
    s_pct numeric(5,3) NOT NULL,
    CONSTRAINT fk_heat_cast FOREIGN KEY (cast_no) REFERENCES mes.casting_sequence (cast_no)
);

COMMENT ON TABLE mes.heat IS '炉次，记录一次转炉冶炼及精炼后的钢水成分';
COMMENT ON COLUMN mes.heat.heat_no IS '炉次号';
COMMENT ON COLUMN mes.heat.cast_no IS '接收本炉钢水的浇次号';
COMMENT ON COLUMN mes.heat.org_id IS '组织编号';
COMMENT ON COLUMN mes.heat.site_id IS '厂区编号';
COMMENT ON COLUMN mes.heat.steel_grade IS '精炼后确认的钢种牌号';
COMMENT ON COLUMN mes.heat.tap_temp_c IS '出钢温度，单位为摄氏度，未测得时为空';
COMMENT ON COLUMN mes.heat.c_pct IS '成品样中碳的质量分数，单位为百分比';
COMMENT ON COLUMN mes.heat.si_pct IS '成品样中硅的质量分数，单位为百分比';
COMMENT ON COLUMN mes.heat.mn_pct IS '成品样中锰的质量分数，单位为百分比';
COMMENT ON COLUMN mes.heat.p_pct IS '成品样中磷的质量分数，单位为百分比';
COMMENT ON COLUMN mes.heat.s_pct IS '成品样中硫的质量分数，单位为百分比';

CREATE TABLE mes.slab (
    slab_no character varying(16) PRIMARY KEY,
    cast_no character varying(16) NOT NULL,
    heat_no character varying(16) NOT NULL,
    org_id character varying(12) NOT NULL,
    site_id character varying(8) NOT NULL,
    thickness_mm smallint NOT NULL,
    width_mm smallint NOT NULL,
    length_mm integer NOT NULL,
    weight_t numeric(8,3) NOT NULL,
    CONSTRAINT fk_slab_cast FOREIGN KEY (cast_no) REFERENCES mes.casting_sequence (cast_no),
    CONSTRAINT fk_slab_heat FOREIGN KEY (heat_no) REFERENCES mes.heat (heat_no)
);

COMMENT ON TABLE mes.slab IS '板坯，记录连铸切割后的定尺钢坯及其冶炼来源';
COMMENT ON COLUMN mes.slab.slab_no IS '板坯号，由炉次流水号和切割顺序标识';
COMMENT ON COLUMN mes.slab.cast_no IS '产出这块板坯的浇次号';
COMMENT ON COLUMN mes.slab.heat_no IS '板坯所属炉次号';
COMMENT ON COLUMN mes.slab.org_id IS '组织编号';
COMMENT ON COLUMN mes.slab.site_id IS '厂区编号';
COMMENT ON COLUMN mes.slab.thickness_mm IS '板坯厚度，单位为毫米';
COMMENT ON COLUMN mes.slab.width_mm IS '板坯宽度，单位为毫米';
COMMENT ON COLUMN mes.slab.length_mm IS '板坯切割长度，单位为毫米';
COMMENT ON COLUMN mes.slab.weight_t IS '板坯理论重量，单位为吨';

CREATE TABLE mes.rolling_event (
    rolling_id character varying(16) PRIMARY KEY,
    org_id character varying(12) NOT NULL,
    site_id character varying(8) NOT NULL,
    started_local timestamp without time zone NOT NULL,
    furnace_exit_c smallint NOT NULL,
    finish_temp_c smallint NOT NULL,
    coiling_temp_c smallint NOT NULL,
    params jsonb NOT NULL
);

COMMENT ON TABLE mes.rolling_event IS '轧制事件，按同一厂区热轧机组的作业批次记录';
COMMENT ON COLUMN mes.rolling_event.rolling_id IS '轧制事件编号';
COMMENT ON COLUMN mes.rolling_event.org_id IS '组织编号';
COMMENT ON COLUMN mes.rolling_event.site_id IS '厂区编号';
COMMENT ON COLUMN mes.rolling_event.started_local IS '轧制开始时间，按厂区当地时间记录';
COMMENT ON COLUMN mes.rolling_event.furnace_exit_c IS '本批板坯平均出炉温度，单位为摄氏度';
COMMENT ON COLUMN mes.rolling_event.finish_temp_c IS '本批带钢平均终轧温度，单位为摄氏度';
COMMENT ON COLUMN mes.rolling_event.coiling_temp_c IS '本批带钢平均卷取温度，单位为摄氏度';
COMMENT ON COLUMN mes.rolling_event.params IS '轧制作业参数，含加热时长（分钟）和粗轧出口厚度（毫米）';

CREATE TABLE mes.slab_rolling (
    slab_no character varying(16) NOT NULL,
    rolling_id character varying(16) NOT NULL,
    PRIMARY KEY (slab_no, rolling_id),
    CONSTRAINT fk_slab_rolling_slab FOREIGN KEY (slab_no) REFERENCES mes.slab (slab_no),
    CONSTRAINT fk_slab_rolling_event FOREIGN KEY (rolling_id) REFERENCES mes.rolling_event (rolling_id)
);

COMMENT ON TABLE mes.slab_rolling IS '板坯参与轧制的记录，一行对应一块板坯参与一个轧制事件';
COMMENT ON COLUMN mes.slab_rolling.slab_no IS '参与轧制的板坯号';
COMMENT ON COLUMN mes.slab_rolling.rolling_id IS '板坯参与的轧制事件编号';

CREATE TABLE mes.coil (
    coil_no character varying(16) PRIMARY KEY,
    rolling_id character varying(16) NOT NULL,
    org_id character varying(12) NOT NULL,
    site_id character varying(8) NOT NULL,
    thickness_mm numeric(5,2) NOT NULL,
    width_mm smallint NOT NULL,
    weight_t numeric(8,3),
    status mes.coil_status NOT NULL,
    CONSTRAINT fk_coil_rolling FOREIGN KEY (rolling_id) REFERENCES mes.rolling_event (rolling_id)
);

COMMENT ON TABLE mes.coil IS '钢卷，记录热轧卷取后的规格、重量和流转状态';
COMMENT ON COLUMN mes.coil.coil_no IS '钢卷号，与来源板坯共用炉次和切割顺序段';
COMMENT ON COLUMN mes.coil.rolling_id IS '完成卷取并产出本钢卷的轧制事件编号';
COMMENT ON COLUMN mes.coil.org_id IS '组织编号';
COMMENT ON COLUMN mes.coil.site_id IS '厂区编号';
COMMENT ON COLUMN mes.coil.thickness_mm IS '成品带钢厚度，单位为毫米';
COMMENT ON COLUMN mes.coil.width_mm IS '成品带钢宽度，单位为毫米';
COMMENT ON COLUMN mes.coil.weight_t IS '钢卷实称重量，单位为吨，未称重时为空';
COMMENT ON COLUMN mes.coil.status IS '钢卷流转状态，区分已产出、已检验、已发运和暂扣';

CREATE TABLE mes.quality_inspection (
    inspection_id uuid PRIMARY KEY,
    coil_no character varying(16) NOT NULL,
    lot_no character varying(20) NOT NULL,
    inspected_on date NOT NULL,
    yield_mpa smallint NOT NULL,
    tensile_mpa smallint NOT NULL,
    elongation_pct numeric(4,1) NOT NULL,
    impact_j smallint NOT NULL,
    passed boolean NOT NULL,
    CONSTRAINT fk_inspection_coil FOREIGN KEY (coil_no) REFERENCES mes.coil (coil_no)
);

COMMENT ON TABLE mes.quality_inspection IS '钢卷质量检验，每行记录一次取样或复检的力学性能和判定';
COMMENT ON COLUMN mes.quality_inspection.inspection_id IS '质检记录唯一标识';
COMMENT ON COLUMN mes.quality_inspection.coil_no IS '取样钢卷号';
COMMENT ON COLUMN mes.quality_inspection.lot_no IS '同一炉次、同厚度规格的检验批号';
COMMENT ON COLUMN mes.quality_inspection.inspected_on IS '完成力学性能检验的日期';
COMMENT ON COLUMN mes.quality_inspection.yield_mpa IS '上屈服强度，单位为兆帕';
COMMENT ON COLUMN mes.quality_inspection.tensile_mpa IS '抗拉强度，单位为兆帕';
COMMENT ON COLUMN mes.quality_inspection.elongation_pct IS '断后伸长率，单位为百分比';
COMMENT ON COLUMN mes.quality_inspection.impact_j IS '二十摄氏度下的冲击吸收能量，单位为焦耳';
COMMENT ON COLUMN mes.quality_inspection.passed IS '本次力学性能检验是否合格';

CREATE TABLE mes.surface_defect (
    defect_id bigint PRIMARY KEY,
    coil_no character varying(16) NOT NULL,
    defect_type text NOT NULL,
    position_m numeric(7,1) NOT NULL,
    severity text NOT NULL,
    CONSTRAINT fk_defect_coil FOREIGN KEY (coil_no) REFERENCES mes.coil (coil_no)
);

COMMENT ON TABLE mes.surface_defect IS '钢卷表面缺陷，记录精整时发现的缺陷类型、位置和严重程度';
COMMENT ON COLUMN mes.surface_defect.defect_id IS '表面缺陷记录编号';
COMMENT ON COLUMN mes.surface_defect.coil_no IS '发现缺陷的钢卷号';
COMMENT ON COLUMN mes.surface_defect.defect_type IS '表面缺陷种类';
COMMENT ON COLUMN mes.surface_defect.position_m IS '缺陷距卷头的长度，单位为米';
COMMENT ON COLUMN mes.surface_defect.severity IS '缺陷严重等级，分为轻微、一般和严重';

CREATE VIEW mes.v_coil_quality AS
SELECT
    c.coil_no,
    c.status,
    count(q.inspection_id) AS inspection_count,
    count(q.inspection_id) FILTER (WHERE q.passed) AS passed_count,
    max(q.inspected_on) AS last_inspected_on
FROM mes.coil AS c
LEFT JOIN mes.quality_inspection AS q ON q.coil_no = c.coil_no
GROUP BY c.coil_no, c.status;

COMMENT ON VIEW mes.v_coil_quality IS '按钢卷汇总检验次数、合格次数和最近检验日期，包含尚未检验的钢卷';
COMMENT ON COLUMN mes.v_coil_quality.coil_no IS '钢卷号';
COMMENT ON COLUMN mes.v_coil_quality.status IS '钢卷当前流转状态';
COMMENT ON COLUMN mes.v_coil_quality.inspection_count IS '钢卷取样及复检的总次数';
COMMENT ON COLUMN mes.v_coil_quality.passed_count IS '钢卷力学性能检验合格的次数';
COMMENT ON COLUMN mes.v_coil_quality.last_inspected_on IS '钢卷最近一次检验的日期，尚未检验时为空';
