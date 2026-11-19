-- 只接受本任务新建、未建立合成账户的 FREEPDB1。SQL*Plus 由准确 ID 控制器调用。
set echo off feedback off verify off heading off pages 0
whenever sqlerror exit failure rollback
alter session set container=FREEPDB1;
create user PRODUCTION no authentication default tablespace USERS quota 16m on USERS;
create user "CaseOwner" no authentication default tablespace USERS quota 16m on USERS;
create user G4_CONTROL no authentication default tablespace USERS quota 16m on USERS;
create user FIXTURE_READER identified by "__READER_PASSWORD__";
grant create session to FIXTURE_READER;
alter user FIXTURE_READER read only;
create table "PRODUCTION"."OMQ_ENTITY" (
    ROW_ID number(18,0) primary key, JOIN_KEY number(12,1), VAL number(28,6),
    ORG_ID varchar2(32 char) not null, SITE_ID varchar2(32 char) not null,
    EXT_ID varchar2(32 char) not null, LABEL varchar2(48 char),
    FROM_TS timestamp(6) not null, TO_TS timestamp(6) not null,
    EVENT_TS timestamp(6) not null, OBSERVED_TS timestamp(6) not null
);
create table "CaseOwner"."OmqTarget" (
    ROW_ID number(18,0) primary key, JOIN_KEY number(13,2), VAL number(28,6),
    ORG_ID varchar2(32 char) not null, SITE_ID varchar2(32 char) not null,
    EXT_ID varchar2(32 char) not null, LABEL varchar2(48 char),
    FROM_TS timestamp(6) not null, TO_TS timestamp(6) not null,
    EVENT_TS timestamp(6) not null, OBSERVED_TS timestamp(6) not null
);
insert into "PRODUCTION"."OMQ_ENTITY" values (
    1, 1.0, 9999999999999999999999.999999, 'org-demo','site-a','omq-entity-1','entity',
    timestamp '2026-01-01 00:00:00.000001',timestamp '2026-02-01 00:00:00.000001',
    timestamp '2026-01-02 00:00:00.123456',timestamp '2026-01-02 00:00:01.654321'
);
insert into "CaseOwner"."OmqTarget" values (
    2, 1.00, -9999999999999999999999.999999, 'org-demo','site-a','omq-target-2','target',
    timestamp '2026-01-01 00:00:00.000001',timestamp '2026-02-01 00:00:00.000001',
    timestamp '2026-01-03 00:00:00.123456',timestamp '2026-01-03 00:00:01.654321'
);
commit;
grant read on "PRODUCTION"."OMQ_ENTITY" to FIXTURE_READER;
grant read on "CaseOwner"."OmqTarget" to FIXTURE_READER;
-- 比对只读 seed 与当期 PUBLIC 差集。除本次四个新用户的默认 INHERIT 外必须完全相同。
-- CHECK_SEED_PUBLIC_IN_CONTROLLER
grant read on SYS.DBA_USERS to G4_CONTROL with grant option;
grant read on SYS.DBA_SYS_PRIVS to G4_CONTROL with grant option;
grant read on SYS.DBA_ROLE_PRIVS to G4_CONTROL with grant option;
grant read on SYS.DBA_TAB_PRIVS to G4_CONTROL with grant option;
grant read on SYS.DBA_COL_PRIVS to G4_CONTROL with grant option;
grant read on SYS.DBA_OBJECTS to G4_CONTROL with grant option;
create table G4_CONTROL.PUBLIC_PRIVILEGE_BASELINE as
    select owner,table_name,privilege,grantable from SYS.DBA_TAB_PRIVS where grantee='PUBLIC';
create view G4_CONTROL.READONLY_ATTESTATION as
    select 'oracle-readonly-v1' POLICY_VERSION,
           (case when exists (select 1 from SYS.DBA_USERS where username='FIXTURE_READER' and read_only='YES') then 0 else 1 end) +
           (case when sys_context('USERENV','CON_NAME')='FREEPDB1' and sys_context('USERENV','SESSION_USER')='FIXTURE_READER' then 0 else 1 end) +
           (select count(*) from SYS.DBA_SYS_PRIVS where grantee in ('FIXTURE_READER','PUBLIC') and (grantee<>'FIXTURE_READER' or privilege<>'CREATE SESSION' or admin_option<>'NO')) +
           (select count(*) from SYS.DBA_ROLE_PRIVS where grantee in ('PUBLIC','FIXTURE_READER')) +
           (select count(*) from SYS.DBA_COL_PRIVS where grantee in ('PUBLIC','FIXTURE_READER')) +
           (select count(*) from (select owner,table_name,privilege,grantable from SYS.DBA_TAB_PRIVS where grantee='PUBLIC' minus select * from G4_CONTROL.PUBLIC_PRIVILEGE_BASELINE)) +
           (select count(*) from (select * from G4_CONTROL.PUBLIC_PRIVILEGE_BASELINE minus select owner,table_name,privilege,grantable from SYS.DBA_TAB_PRIVS where grantee='PUBLIC')) +
           (select count(*) from SYS.DBA_TAB_PRIVS where grantee='FIXTURE_READER' and (privilege<>'READ' or grantable<>'NO' or
                    (owner,table_name) not in (('PRODUCTION','OMQ_ENTITY'),('CaseOwner','OmqTarget'),('G4_CONTROL','READONLY_ATTESTATION')))) +
           (select count(*) from SYS.DBA_TAB_PRIVS p join SYS.DBA_OBJECTS o on o.owner=p.owner and o.object_name=p.table_name
              where p.grantee in ('FIXTURE_READER','PUBLIC') and o.object_type in ('DIRECTORY','LIBRARY')) +
           abs(3-(select count(*) from SYS.DBA_TAB_PRIVS where grantee='FIXTURE_READER')) +
           (select count(*) from SYS.DBA_OBJECTS where owner='FIXTURE_READER') BLOCKED_COUNT from dual;
grant read on G4_CONTROL.READONLY_ATTESTATION to FIXTURE_READER;
exit success
