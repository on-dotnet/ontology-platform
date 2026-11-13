-- 只在准确G4-M2-ORACLE-01全新合成PDB执行；口令由控制器内存替换。
set echo off feedback off heading off pages 0
whenever sqlerror exit failure rollback
alter session set container=FREEPDB1;
create user PRODUCTION no authentication default tablespace USERS quota 16m on USERS;
create user "CaseOwner" no authentication default tablespace USERS quota 16m on USERS;
create user G4_CONTROL no authentication default tablespace USERS quota 16m on USERS;
create user FIXTURE_READER identified by "__READER_PASSWORD__";
grant create session to FIXTURE_READER;
alter user FIXTURE_READER read only;
create table PRODUCTION.METADATA_TYPES (
  ID number(10,0) not null,
  UNDECLARED_NUMBER number,
  NEGATIVE_SCALE number(10,-2),
  DAY_AND_TIME date,
  FRACTIONAL_TIME timestamp(9),
  ZONED_TIME timestamp(6) with time zone,
  LOCAL_TIME timestamp(3) with local time zone,
  BYTE_TEXT varchar2(24 byte),
  CHAR_TEXT varchar2(24 char),
  NATIONAL_TEXT nvarchar2(24),
  LARGE_TEXT clob,
  BINARY_CONTENT blob
);
create table "CaseOwner"."MixedCase" ("Key" number, "TextValue" varchar2(32 char));
create view PRODUCTION.METADATA_VIEW as select ID, UNDECLARED_NUMBER from PRODUCTION.METADATA_TYPES;
grant read on PRODUCTION.METADATA_TYPES to FIXTURE_READER;
grant read on PRODUCTION.METADATA_VIEW to FIXTURE_READER;
grant read on "CaseOwner"."MixedCase" to FIXTURE_READER;
-- 仅固定证明视图的无登录拥有者读取管理字典，产品不获这些授权。
grant read on SYS.DBA_USERS to G4_CONTROL with grant option;
grant read on SYS.DBA_SYS_PRIVS to G4_CONTROL with grant option;
grant read on SYS.DBA_ROLE_PRIVS to G4_CONTROL with grant option;
grant read on SYS.DBA_TAB_PRIVS to G4_CONTROL with grant option;
grant read on SYS.DBA_COL_PRIVS to G4_CONTROL with grant option;
grant read on SYS.DBA_OBJECTS to G4_CONTROL with grant option;
-- 控制器须先核验当前PUBLIC与只读PDB$SEED唯一差异为上述四个用户的默认INHERIT PRIVILEGES。
-- 没有来源/精确集合比较成功，不得执行以下基线创建。
create table G4_CONTROL.PUBLIC_PRIVILEGE_BASELINE as
  select owner,table_name,privilege,grantable from DBA_TAB_PRIVS where grantee='PUBLIC';
-- 有界取消夹具只改变等待时间，不开放调用方SQL或写操作。
create table G4_CONTROL.DELAY_CONTROL (ID number primary key, SECONDS number check (SECONDS between 0 and 10));
insert into G4_CONTROL.DELAY_CONTROL values (1,0);
commit;
create function G4_CONTROL.DELAY_GATE return number authid definer as
  delay_seconds number;
begin
  select SECONDS into delay_seconds from G4_CONTROL.DELAY_CONTROL where ID=1;
  for tick in 1..ceil(least(delay_seconds,10)*20) loop
    SYS.DBMS_SESSION.SLEEP(0.05);
  end loop;
  return 0;
end;
/
create view G4_CONTROL.READONLY_ATTESTATION as
select 'oracle-readonly-v1' POLICY_VERSION,
  G4_CONTROL.DELAY_GATE() +
  (case when exists (select 1 from SYS.DBA_USERS where username='FIXTURE_READER' and read_only='YES') then 0 else 1 end) +
  (case when SYS_CONTEXT('USERENV','CON_NAME')='FREEPDB1' and SYS_CONTEXT('USERENV','SESSION_USER')='FIXTURE_READER' then 0 else 1 end) +
  (select count(*) from SYS.DBA_SYS_PRIVS where grantee in ('FIXTURE_READER','PUBLIC') and (grantee='PUBLIC' or privilege<>'CREATE SESSION' or admin_option<>'NO')) +
  (select count(*) from SYS.DBA_ROLE_PRIVS where grantee in ('FIXTURE_READER','PUBLIC')) +
  (select count(*) from SYS.DBA_COL_PRIVS where grantee in ('FIXTURE_READER','PUBLIC') and privilege<>'SELECT') +
  (select count(*) from SYS.DBA_TAB_PRIVS p where grantee='PUBLIC' and not exists
    (select 1 from G4_CONTROL.PUBLIC_PRIVILEGE_BASELINE b where b.owner=p.owner and b.table_name=p.table_name and b.privilege=p.privilege and b.grantable=p.grantable)) +
  (select count(*) from SYS.DBA_TAB_PRIVS p join SYS.DBA_OBJECTS o on o.owner=p.owner and o.object_name=p.table_name where p.grantee in ('FIXTURE_READER','PUBLIC') and o.object_type in ('DIRECTORY','LIBRARY')) +
  (select count(*) from SYS.DBA_TAB_PRIVS where grantee='FIXTURE_READER' and
    (privilege<>'READ' or grantable<>'NO' or not (owner in ('PRODUCTION','CaseOwner') or (owner='G4_CONTROL' and table_name='READONLY_ATTESTATION')))) +
  (select count(*) from SYS.DBA_OBJECTS where owner='FIXTURE_READER') BLOCKED_COUNT
from DUAL;
grant read on G4_CONTROL.READONLY_ATTESTATION to FIXTURE_READER;
select 'FIXTURE_CREATED_READ_ONLY='||read_only from DBA_USERS where username='FIXTURE_READER';
exit
