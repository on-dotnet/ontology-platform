-- 只在本任务新 FREEPDB1 创建。观察者无管理权；视图规定两个固定 SQL、唯一模块、读者和 PDB。
set echo off feedback off verify off heading off pages 0
whenever sqlerror exit failure rollback
alter session set container=FREEPDB1;
create user OMQ_OBSERVER identified by "__OBSERVER_PASSWORD__";
revoke inherit privileges on user OMQ_OBSERVER from PUBLIC;
grant create session to OMQ_OBSERVER;
alter user OMQ_OBSERVER read only;
grant select on SYS.V_$SESSION to G4_CONTROL with grant option;
grant select on SYS.V_$SQL to G4_CONTROL with grant option;
grant select on SYS.V_$SQL_PLAN to G4_CONTROL with grant option;
grant select on AUDSYS.UNIFIED_AUDIT_TRAIL to G4_CONTROL with grant option;
create view G4_CONTROL.OMQ_SESSIONS as
    select sid,serial# serial_no,audsid,con_id,client_identifier,sql_id,sql_exec_start,sql_exec_id,
           prev_sql_id,prev_exec_start,prev_exec_id,status,state,event
    from SYS.V_$SESSION
    where con_id=to_number(sys_context('USERENV','CON_ID')) and username='FIXTURE_READER'
      and module='G4-ORACLE-MAPPING-QUERY-001' and regexp_like(client_identifier,'^[a-f0-9]{32}$');
create view G4_CONTROL.OMQ_CURSOR_STATS as
    select sql_id,child_number,plan_hash_value,executions,end_of_fetch_count,rows_processed,elapsed_time,px_servers_executions
    from SYS.V_$SQL
    where con_id=to_number(sys_context('USERENV','CON_ID')) and parsing_schema_name='FIXTURE_READER'
      and sql_id in ('__ENTITY_SQL_ID__','__TARGET_SQL_ID__');
create view G4_CONTROL.OMQ_PLAN as
    select p.sql_id,p.child_number,p.id,p.parent_id,p.operation,p.options
      from SYS.V_$SQL_PLAN p join G4_CONTROL.OMQ_CURSOR_STATS c on c.sql_id=p.sql_id and c.child_number=p.child_number
     where p.con_id=to_number(sys_context('USERENV','CON_ID'));
create audit policy OMQ_FIXED_READS actions select on "PRODUCTION"."OMQ_ENTITY", select on "CaseOwner"."OmqTarget";
audit policy OMQ_FIXED_READS by FIXTURE_READER;
create view G4_CONTROL.OMQ_READ_AUDIT as
    select instance_id,sessionid,entry_id,statement_id,execution_id,client_identifier,object_schema,
           object_name,action_name,return_code,event_timestamp_utc
    from AUDSYS.UNIFIED_AUDIT_TRAIL
    where dbusername='FIXTURE_READER' and action_name='SELECT'
      and regexp_like(client_identifier,'^[a-f0-9]{32}$')
      and (object_schema,object_name) in (('PRODUCTION','OMQ_ENTITY'),('CaseOwner','OmqTarget'))
      and instr(unified_audit_policies,'OMQ_FIXED_READS')>0;
grant read on G4_CONTROL.OMQ_SESSIONS to OMQ_OBSERVER;
grant read on G4_CONTROL.OMQ_CURSOR_STATS to OMQ_OBSERVER;
grant read on G4_CONTROL.OMQ_PLAN to OMQ_OBSERVER;
grant read on G4_CONTROL.OMQ_READ_AUDIT to OMQ_OBSERVER;
exit success
