-- 仅本任务全新合成源；执行器在私有副本中替换随机只读密码。
REVOKE ALL ON DATABASE fixture FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE UPDATE ON pg_catalog.pg_settings FROM PUBLIC;
CREATE ROLE fixture_reader LOGIN PASSWORD '__MAPPING_READER_PASSWORD__' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
GRANT CONNECT ON DATABASE fixture TO fixture_reader;
ALTER ROLE fixture_reader SET default_transaction_read_only = on;
ALTER ROLE fixture_reader SET statement_timeout = '5s';
CREATE SCHEMA production;
-- 显式允许已证明无对象的public目录探测；不授予CREATE或任何写权限。
GRANT USAGE ON SCHEMA production, public TO fixture_reader;
CREATE TABLE production.assets (
    organization_id text NOT NULL,
    site_id text NOT NULL,
    asset_id text NOT NULL,
    valid_from timestamptz NOT NULL,
    valid_to timestamptz NOT NULL,
    label text NOT NULL,
    PRIMARY KEY (organization_id, site_id, asset_id, valid_from)
);
CREATE TABLE production.readings (
    organization_id text NOT NULL,
    site_id text NOT NULL,
    reading_id text NOT NULL,
    asset_id text NOT NULL,
    valid_from timestamptz NOT NULL,
    valid_to timestamptz NOT NULL,
    observed_at timestamptz NOT NULL,
    temperature numeric(12,4) NOT NULL,
    unit_code text NOT NULL,
    attributes jsonb NOT NULL,
    PRIMARY KEY (organization_id, site_id, reading_id, valid_from)
);
INSERT INTO production.assets VALUES
 ('org-demo','site-a','asset-1','2026-01-01T00:00:00Z','2027-01-01T00:00:00Z','合成设备A'),
 ('org-demo','site-b','asset-1','2026-01-01T00:00:00Z','2027-01-01T00:00:00Z','合成设备B');
INSERT INTO production.readings VALUES
 ('org-demo','site-a','reading-1','asset-1','2026-11-14T00:00:00Z','2026-11-14T00:01:00Z','2026-11-14T00:00:01.123456Z',20.1250,'Cel','{"quality":"good"}'),
 ('org-demo','site-a','reading-2','asset-1','2026-11-14T00:01:00Z','2026-11-14T00:02:00Z','2026-11-14T00:01:01Z',21.0000,'Cel','{"quality":"good"}'),
 ('org-demo','site-b','reading-1','asset-1','2026-11-14T00:00:00Z','2026-11-14T00:01:00Z','2026-11-14T00:00:01Z',22.0000,'Cel','{"quality":"good"}');
GRANT SELECT ON production.assets, production.readings TO fixture_reader;
-- 预算负例独立表，不影响首条正常映射限定集合。
CREATE TABLE production.readings_overflow (LIKE production.readings INCLUDING ALL);
INSERT INTO production.readings_overflow
SELECT 'org-demo','site-a','overflow-' || value,'asset-1',
 '2026-11-14T00:00:00Z'::timestamptz,'2026-11-14T00:01:00Z'::timestamptz,
 '2026-11-14T00:00:01Z'::timestamptz,20.1250,'Cel','{"quality":"good"}'::jsonb
FROM generate_series(1,101) value;
GRANT SELECT ON production.readings_overflow TO fixture_reader;

-- 单行超大JSON负例，源端必须在发送值之前返回预算哨兵。
CREATE TABLE production.readings_oversized (LIKE production.readings INCLUDING ALL);
INSERT INTO production.readings_oversized
SELECT 'org-demo','site-a','oversized','asset-1',
 '2026-11-14T00:00:00Z'::timestamptz,'2026-11-14T00:01:00Z'::timestamptz,
 '2026-11-14T00:00:01Z'::timestamptz,20.1250,'Cel',jsonb_build_object('payload',repeat('x',4194304));
GRANT SELECT ON production.readings_oversized TO fixture_reader;

-- varchar也是受支持变长类型，不能在客户端物化后才执行预算。
CREATE TABLE production.readings_varchar (LIKE production.readings INCLUDING ALL);
ALTER TABLE production.readings_varchar ALTER COLUMN unit_code TYPE varchar(5000000);
INSERT INTO production.readings_varchar
SELECT 'org-demo','site-a','oversized-varchar','asset-1',
 '2026-11-14T00:00:00Z'::timestamptz,'2026-11-14T00:01:00Z'::timestamptz,
 '2026-11-14T00:00:01Z'::timestamptz,20.1250,repeat('x',4194304),'{}'::jsonb;
GRANT SELECT ON production.readings_varchar TO fixture_reader;
