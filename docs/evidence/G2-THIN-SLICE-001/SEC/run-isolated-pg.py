#!/usr/bin/env python3
"""Run G2 SEC tests against a new disposable PostgreSQL container only.

Uses the approved immutable image, loopback random port and tmpfs. Random test
password and connection string stay in child environment/in-memory redaction.
No Keycloak, historical runtime, retained volume, or credential file is read.
"""
from pathlib import Path
import os
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
IMAGE = "postgres:18.6-trixie@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6"


def main():
    name = "g2-sec-test-" + secrets.token_hex(6)
    database_password = secrets.token_urlsafe(40)
    env = os.environ.copy()
    env.update(POSTGRES_PASSWORD=database_password, POSTGRES_DB="governance")
    connection = ""
    try:
        subprocess.run(["docker", "run", "--detach", "--name", name, "--env", "POSTGRES_PASSWORD", "--env", "POSTGRES_DB", "--publish", "127.0.0.1::5432", "--tmpfs", "/var/lib/postgresql", IMAGE], env=env, check=True, stdout=subprocess.DEVNULL)
        port = subprocess.check_output(["docker", "port", name, "5432/tcp"], text=True).strip().rsplit(":", 1)[1]
        for _ in range(60):
            if subprocess.run(["docker", "exec", name, "pg_isready", "-U", "postgres", "-d", "governance"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                break
            time.sleep(1)
        else:
            raise TimeoutError("temporary PostgreSQL readiness")
        connection = f"Host=127.0.0.1;Port={port};Database=governance;Username=postgres;Password={database_password}"
        env["G1_SEC_PG_CONNECTION"] = connection
        command = ["dotnet", "test", "--project", "backend/tests/OntologyPlatform.SecurityTests", "--no-restore", "--filter", "FullyQualifiedName~G2SecurityTests|FullyQualifiedName~G2AuditTransactionTests"]
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        print(result.stdout.replace(connection, "[REDACTED_CONNECTION]").replace(database_password, "[REDACTED_PASSWORD]"))
        print(f"SEC isolated PG test exitCode={result.returncode}")
        return result.returncode
    except Exception as failure:
        print("SEC isolated PG fixture failure category=" + type(failure).__name__)
        return 1
    finally:
        subprocess.run(["docker", "rm", "--force", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    sys.exit(main())
