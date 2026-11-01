namespace OntologyPlatform.Modules.Connections;

/// <summary>适配器唯一SQL白名单；所有查询只访问系统目录，不执行用户可定义函数。</summary>
public sealed partial class PgSourceAdapter
{
    /// <summary>保守检查全部直接及间接成员角色，包括可SET ROLE但未自动继承的写入能力。</summary>
    private const string ReadOnlySql = """
        WITH reachable AS (
            SELECT r.* FROM pg_catalog.pg_roles r
            WHERE r.rolname = current_user OR pg_catalog.pg_has_role(current_user, r.oid, 'MEMBER')
        )
        SELECT current_user = 'fixture_reader' AND session_user = 'fixture_reader'
            AND current_database() = 'fixture'
            AND current_setting('transaction_read_only') = 'on'
            AND NOT EXISTS (
                SELECT 1 FROM reachable r
                WHERE r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolbypassrls OR r.rolreplication
                    OR r.rolname IN ('pg_write_all_data', 'pg_write_server_files', 'pg_execute_server_program',
                        'pg_signal_backend', 'pg_checkpoint', 'pg_maintain', 'pg_database_owner')
                    OR pg_catalog.has_database_privilege(r.oid, current_database(), 'CREATE,TEMP')
                    OR EXISTS (SELECT 1 FROM pg_catalog.pg_shdepend d WHERE d.refclassid = 'pg_catalog.pg_authid'::regclass
                        AND d.refobjid = r.oid AND d.deptype = 'o')
                    OR EXISTS (SELECT 1 FROM pg_catalog.pg_namespace n
                        WHERE n.nspowner = r.oid OR pg_catalog.has_schema_privilege(r.oid, n.oid, 'CREATE'))
                    OR EXISTS (SELECT 1 FROM pg_catalog.pg_class c WHERE c.relowner = r.oid)
                    OR EXISTS (SELECT 1 FROM pg_catalog.pg_proc p WHERE p.proowner = r.oid)
                    OR EXISTS (SELECT 1 FROM pg_catalog.pg_type t WHERE t.typowner = r.oid)
                    OR EXISTS (SELECT 1 FROM pg_catalog.pg_class c
                        WHERE c.relkind IN ('r','p','v','m','f') AND (
                            pg_catalog.has_table_privilege(r.oid, c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
                            OR pg_catalog.has_any_column_privilege(r.oid, c.oid, 'INSERT,UPDATE,REFERENCES')))
                    OR EXISTS (SELECT 1 FROM pg_catalog.pg_class c
                        WHERE CASE WHEN c.relkind = 'S' THEN pg_catalog.has_sequence_privilege(r.oid, c.oid, 'USAGE,UPDATE') ELSE false END)
            )
        """;

    /// <summary>源端LIMIT哨兵、逐列SELECT权限和系统format_type保真，不读取业务数据。</summary>
    private const string CatalogSql = """
        WITH visible_objects AS MATERIALIZED (
            SELECT c.oid, n.nspname, c.relname, c.relkind
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = ANY(@schemas)
                AND pg_catalog.has_schema_privilege(n.oid, 'USAGE')
                AND c.relkind IN ('r','p','v','m','f')
                AND (pg_catalog.has_table_privilege(c.oid, 'SELECT') OR pg_catalog.has_any_column_privilege(c.oid, 'SELECT'))
            ORDER BY n.nspname COLLATE "C", c.relname COLLATE "C"
            LIMIT 101
        )
        SELECT o.nspname, o.relname, CASE WHEN o.relkind IN ('v','m') THEN 'VIEW' ELSE 'TABLE' END,
            a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod), NOT (a.attnotnull OR t.typnotnull), a.attnum,
            CASE WHEN bt.oid = 1700 AND m.typmod >= 4 THEN ((m.typmod - 4) >> 16) & 65535 END,
            CASE WHEN bt.oid = 1700 AND m.typmod >= 4 THEN (((m.typmod - 4) & 2047) # 1024) - 1024 END
        FROM visible_objects o
        LEFT JOIN pg_catalog.pg_attribute a ON a.attrelid = o.oid AND a.attnum > 0 AND NOT a.attisdropped
            AND pg_catalog.has_column_privilege(o.oid, a.attnum, 'SELECT')
        LEFT JOIN pg_catalog.pg_type t ON t.oid = a.atttypid
        LEFT JOIN pg_catalog.pg_type bt ON bt.oid = CASE WHEN t.typtype = 'd' THEN t.typbasetype ELSE t.oid END
        LEFT JOIN LATERAL (SELECT CASE WHEN t.typtype = 'd' THEN t.typtypmod ELSE a.atttypmod END AS typmod) m ON true
        ORDER BY o.nspname COLLATE "C", o.relname COLLATE "C", a.attnum
        LIMIT 2001
        """;
}
