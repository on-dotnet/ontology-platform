"""在源内部网络把准确观察结果发给该次命令，无宿主端口、SQL 正文或业务值。"""
import ipaddress
import re

from workflow_oracle_mapping_resources import require


def native_trigger(execution, source_sql, probe_ip):
    require(re.fullmatch('[0-9a-f]{32}',execution) and re.fullmatch('[0-9a-z]{13}',source_sql),'TRIGGER_IDENTITY')
    require(ipaddress.ip_address(probe_ip).version == 4 and ipaddress.ip_address(probe_ip).is_private,'TRIGGER_PEER')
    # 两端均预先打开。源侧 shell 只收到窄只读视图的结果，触发信号不经过宿主轮询。
    relay = r"""set -euo pipefail
exec 3>/dev/udp/"$1"/28761
stdbuf -oL sqlplus -L -s /nolog | while IFS= read -r row; do
  case "$row" in
    OMQ_READY) printf '%s|READY' "$2" >&3 ;;
    ACTIVE\|*) printf '%s|ACTIVE' "$2" >&3 ;;
    NATURAL\|*) printf '%s|NATURAL' "$2" >&3 ;;
    MISSED\|*) printf '%s|MISSED' "$2" >&3 ;;
  esac
  printf '%s\n' "$row"
done"""
    sql = """prompt OMQ_READY
declare
  stop_at timestamp with time zone:=systimestamp+numtodsinterval(0.88,'SECOND');
  left_at timestamp with time zone; right_at timestamp with time zone;
  seen number; identity_text varchar2(300); current_id varchar2(13); current_exec number;
  previous_id varchar2(13); previous_exec number; active varchar2(8); waited varchar2(60);
  samples number:=0; result varchar2(16):='MISSED';
begin
  while systimestamp < stop_at loop
    left_at:=systimestamp;
    select count(*),max(sid||'|'||serial_no||'|'||audsid||'|'||con_id),
           max(sql_id),max(sql_exec_id),max(prev_sql_id),max(prev_exec_id),max(status),max(event)
      into seen,identity_text,current_id,current_exec,previous_id,previous_exec,active,waited
      from G4_CONTROL.OMQ_SESSIONS where client_identifier='{execution}';
    right_at:=systimestamp;
    samples:=samples+1;
    if seen>1 then raise_application_error(-20009,'nonunique observer identity'); end if;
    if seen=1 and current_id='{sqlid}' and current_exec is not null and active='ACTIVE' then
      result:='ACTIVE'; exit;
    elsif seen=1 and previous_id='{sqlid}' and previous_exec is not null and active='INACTIVE' then
      result:='NATURAL'; exit;
    end if;
  end loop;
  dbms_output.put_line(result||'|'||to_char(sys_extract_utc(left_at),'YYYY-MM-DD"T"HH24:MI:SS.FF6')||'|'||
    to_char(sys_extract_utc(right_at),'YYYY-MM-DD"T"HH24:MI:SS.FF6')||'|'||seen||'|'||identity_text||'|'||
    current_id||'|'||current_exec||'|'||previous_id||'|'||previous_exec||'|'||active||'|'||waited||'|'||samples);
end;
/
""".format(execution=execution,sqlid=source_sql)
    return ['bash','-c',relay,'task-local-observer',probe_ip,execution],sql
