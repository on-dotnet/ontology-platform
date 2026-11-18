"""仅对本任务已审两个合成平台库暂时封闭持久投递，退出时回滚。"""
from contextlib import ExitStack, contextmanager
import os
import re
from pathlib import Path
import tempfile
import uuid
import selectors
import subprocess
import time


TABLES = ('semantic_query."Queries"', 'agents."Runs"', 'connections."CatalogJobs"', 'connections."ConnectionProbes"')
COUNTS = (
    '''SELECT count(*) FROM semantic_query."Queries" WHERE "ExecutionStatus"='RUNNING' ''',
    '''SELECT count(*) FROM agents."Runs" WHERE "Status" IN ('QUEUED','RUNNING') ''',
    '''SELECT count(*) FROM connections."CatalogJobs" WHERE "Status" IN ('QUEUED','RUNNING') ''',
    '''SELECT count(*) FROM connections."ConnectionProbes" WHERE "ReportJson"::jsonb->>'status'='RUNNING' OR "ReportJson"::jsonb->>'Status'='RUNNING' ''',
    '''SELECT count(*) FROM publishing."Outbox" WHERE "DispatchedAtUtc" IS NULL''',
)
SCHEMAS = ('agents', 'connections', 'governance', 'ontology', 'publishing', 'semantic_query')
ACTIVITY = """SELECT count(*) FROM pg_stat_activity WHERE datname=current_database()
AND backend_type='client backend' AND pid<>pg_backend_pid()
AND state IS DISTINCT FROM 'idle'"""


def psql(row):
    platform = row['service'] == 'platform-pg'
    return ['docker', '--context', 'desktop-linux', 'exec', '-i', '-e', 'PGAPPNAME=dmq-cold-fence',
            row['containerId'], 'psql', '-X', '-w', '-qAt', '-v', 'ON_ERROR_STOP=1',
            '-U', 'postgres', '-d', 'query' if platform else 'fixture']


def retain_error(raw):
    if not raw:
        return
    path = Path(__file__).resolve().parents[2] / 'artifacts/workflow/G4-DORIS-MAPPING-QUERY-001/cold-save-01/private-errors'
    if path.resolve() != path:
        raise ValueError('LINKED_ERROR_PATH')
    path.mkdir(mode=0o700, exist_ok=True, parents=True)
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError('PRIVATE_ERROR_MODE')
    with os.fdopen(os.open(path / (uuid.uuid4().hex + '.stderr'), os.O_WRONLY | os.O_EXCL | os.O_CREAT, 0o600), 'wb') as stream:
        stream.write(raw)


def query(row, sql):
    result = subprocess.run(psql(row), input=sql.encode(), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=8, check=False)
    retain_error(result.stderr)
    if result.returncode:
        raise ValueError('PG_CHECK_FAILED_' + row['service'] + '_' + str(result.returncode))
    return result.stdout.decode().splitlines()


@contextmanager
def fence(row, tables):
    errors = tempfile.TemporaryFile()
    process = subprocess.Popen(psql(row), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
    try:
        sql = ("BEGIN; SET LOCAL idle_in_transaction_session_timeout='14min'; LOCK TABLE "
               + ', '.join(tables) + " IN SHARE MODE NOWAIT; SELECT 'FENCED-' || pg_backend_pid();\n")
        process.stdin.write(sql.encode())
        process.stdin.flush()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            tag = os.read(process.stdout.fileno(), 32).strip() if selector.select(7) else b''
            found = re.fullmatch(rb'FENCED-([1-9][0-9]*)', tag)
            if not found:
                raise ValueError('PG_FENCE_NOT_ACQUIRED')
        yield int(found.group(1))
    finally:
        if process.poll() is None:
            try:
                process.stdin.write(b'ROLLBACK;\n')
                process.stdin.close()
            except BrokenPipeError:
                pass
        process.wait(timeout=10)
        process.stdout.close()
        errors.seek(0)
        retain_error(errors.read())
        errors.close()


def product_tables(row):
    sql = ("SELECT n.nspname || '.' || quote_ident(c.relname) FROM pg_class c JOIN pg_namespace n "
           "ON n.oid=c.relnamespace WHERE c.relkind IN ('r','p') AND n.nspname IN ("
           + ','.join("'" + name + "'" for name in SCHEMAS) + ") ORDER BY 1;")
    tables = query(row, sql)
    if not set(TABLES).issubset(tables) or not all(re.fullmatch(r'[a-z_]+\.(?:"[A-Za-z0-9_]+"|[a-z_][a-z_0-9]*)', t)
                                                 for t in tables):
        raise ValueError('PG_TABLE_INVENTORY')
    return tables


def confirm(row, tables):
    statements = []
    for table in tables:
        statements.append(f'DO $$ BEGIN LOCK TABLE {table} IN ROW EXCLUSIVE MODE NOWAIT; '
               "RAISE EXCEPTION 'unexpected unlocked table'; EXCEPTION WHEN lock_not_available THEN NULL; END $$;")
    query(row, "\n".join(statements))


def sample(rows, fence_pids=None):
    snapshot = {}
    for row in rows:
        pid = (fence_pids or {}).get(row['containerId'])
        if pid is not None and (type(pid) is not int or pid <= 0):
            raise ValueError('PG_FENCE_PID')
        activity = ACTIVITY if pid is None else ACTIVITY + ' AND pid<>' + str(pid)
        statements = [*COUNTS, activity] if row['service'] == 'platform-pg' else [activity]
        values = [int(x) for x in query(row, ';'.join(statements) + ';')]
        if len(values) != len(statements):
            raise ValueError('DRAIN_SAMPLE_INCOMPLETE')
        snapshot[row['containerId']] = values
    return snapshot


@contextmanager
def drained(inventory, on_failed_sample=None):
    databases = [row for row in inventory if row['service'] in ('platform-pg', 'pg-source')]
    platforms = [row for row in databases if row['service'] == 'platform-pg']
    if len(databases) != 4 or len(platforms) != 2:
        raise ValueError('DATABASE_ALLOWLIST_MISMATCH')
    tables = {row['containerId']: product_tables(row) for row in platforms}
    deadline = time.monotonic() + 30
    while True:
        with ExitStack() as stack:
            before = sample(databases)
            if not any(any(row) for row in before.values()):
                fence_pids = {row['containerId']: stack.enter_context(fence(row, tables[row['containerId']])) for row in platforms}
                after = sample(databases, fence_pids)
                if not any(any(row) for row in after.values()):
                    for row in platforms:
                        confirm(row, tables[row['containerId']])
                    def check():
                        for row in platforms:
                            confirm(row, tables[row['containerId']])
                        current = sample(databases, fence_pids)
                        if any(any(v) for v in current.values()):
                            if on_failed_sample:
                                on_failed_sample(current)
                            raise ValueError('DRAIN_ACTIVITY_DETECTED')
                        return current
                    yield {'before': before, 'fenced': after, 'writerConflictChecks': sum(map(len, tables.values())), 'tables': tables}, check
                    return
        if time.monotonic() >= deadline:
            raise ValueError('DRAIN_DEADLINE')
        time.sleep(0.5)
