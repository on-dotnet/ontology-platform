#!/usr/bin/env python3
"""仅生成 G4-M1-RECOVERY-001 私有合成 PG 输入；不启动容器、不联网、不改系统信任。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

TASK = "G4-M1-RECOVERY-001"
ROOT = Path(__file__).resolve().parents[2]


def run_openssl(executable, directory, arguments):
    """只调用既有工具，参数不含密码，工具诊断不进入普通日志。"""
    result = subprocess.run([executable, *arguments], cwd=directory, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, timeout=30, check=False)
    if result.returncode:
        raise RuntimeError("OPENSSL_FAILED_EXIT_" + str(result.returncode))


def private_file(directory, name, content):
    """独占创建0600文件，不覆盖已有私有输入。"""
    with open(directory / name, "x", encoding="utf-8",
              opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        stream.write(content)


def generate(directory):
    """限定本树私有任务目录，生成证书、无业务行SQL及容器内路径输入。"""
    executable = shutil.which("openssl")
    if not executable:
        raise RuntimeError("EXISTING_OPENSSL_REQUIRED")
    directory = directory.absolute()
    private_root = ROOT / ".tools" / "security"
    if directory.parent != private_root or not directory.name.startswith("g4-m1-recovery-001-"):
        raise ValueError("TASK_PRIVATE_DIRECTORY_REQUIRED")
    if any(path.is_symlink() for path in (ROOT / ".tools", private_root, directory)):
        raise ValueError("SYMLINK_REFUSED")
    if directory.exists():
        raise ValueError("EXISTING_DIRECTORY_PRESERVED")
    private_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    previous_umask = os.umask(0o077)
    try:
        for prefix in ("ca", "wrong-ca"):
            run_openssl(executable, directory, ["req", "-x509", "-newkey", "rsa:2048", "-noenc", "-sha256", "-days", "7",
                "-subj", "/CN=OntologyPlatform Synthetic " + prefix, "-addext", "basicConstraints=critical,CA:TRUE",
                "-addext", "keyUsage=critical,keyCertSign,cRLSign", "-keyout", prefix + ".key", "-out", prefix + ".crt"])
        for prefix, hostname in (("server", "pg-source"), ("wrong-san", "wrong-source.invalid")):
            run_openssl(executable, directory, ["req", "-new", "-newkey", "rsa:2048", "-noenc", "-sha256",
                "-subj", "/CN=" + hostname, "-keyout", prefix + ".key", "-out", prefix + ".csr"])
            private_file(directory, prefix + ".ext", "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:" + hostname + "\n")
            run_openssl(executable, directory, ["x509", "-req", "-in", prefix + ".csr", "-CA", "ca.crt", "-CAkey", "ca.key",
                "-set_serial", "0x" + secrets.token_hex(16), "-days", "7", "-sha256", "-extfile", prefix + ".ext", "-out", prefix + ".crt"])
        reader_password = secrets.token_urlsafe(36)
        private_file(directory, "reader-password", reader_password)
        private_file(directory, "postgres-password", secrets.token_urlsafe(36))
        # token_urlsafe只含字母、数字、下划线及连字符；值只在0600初始化文件中，不传入进程参数。
        private_file(directory, "init.sql", """\\set ON_ERROR_STOP on
CREATE ROLE fixture_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD '%s';
REVOKE CREATE, TEMPORARY ON DATABASE fixture FROM PUBLIC;
REVOKE ALL ON DATABASE fixture FROM fixture_reader;
GRANT CONNECT ON DATABASE fixture TO fixture_reader;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE UPDATE ON pg_catalog.pg_settings FROM PUBLIC;
CREATE SCHEMA production AUTHORIZATION postgres;
CREATE SCHEMA maintenance AUTHORIZATION postgres;
CREATE SCHEMA otherplant AUTHORIZATION postgres;
REVOKE ALL ON SCHEMA production, maintenance, otherplant FROM PUBLIC;
REVOKE ALL ON SCHEMA production, maintenance, otherplant FROM fixture_reader;
CREATE TABLE production.heat_event (
    id bigint PRIMARY KEY,
    tap_temp numeric(8,2),
    tap_ts timestamp without time zone,
    event_time timestamp with time zone,
    payload jsonb,
    tags text[],
    nullable text NULL
);
CREATE TABLE maintenance.private_event (id bigint);
CREATE TABLE otherplant.private_event (id bigint);
REVOKE ALL ON ALL TABLES IN SCHEMA production, maintenance, otherplant FROM PUBLIC;
GRANT USAGE ON SCHEMA production TO fixture_reader;
GRANT SELECT ON production.heat_event TO fixture_reader;
ALTER ROLE fixture_reader IN DATABASE fixture SET default_transaction_read_only = on;
""" % reader_password)
        private_file(directory, "pg_hba.conf", """# Only this task's isolated synthetic source network; no host port is published.
local all postgres trust
local all all reject
hostnossl all all all reject
hostssl fixture fixture_reader all scram-sha-256
hostssl all all all reject
""")
        private_file(directory, "adapter-input.json", json.dumps({
            "fixtureIdentity": TASK,
            "secretFile": "/run/secrets/reader-password",
            "rootCertificatePath": "/run/secrets/ca.crt",
            "wrongRootCertificatePath": "/run/secrets/wrong-ca.crt"
        }, indent=2) + "\n")
        # 中间CSR、扩展配置及CA私钥仅属于本次生成过程，签发完成后精确移除。
        for name in ("ca.key", "wrong-ca.key", "server.csr", "server.ext", "wrong-san.csr", "wrong-san.ext"):
            (directory / name).unlink()
        for path in directory.iterdir():
            path.chmod(0o600)
        certificates = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                        for name in ("ca.crt", "wrong-ca.crt", "server.crt", "wrong-san.crt")}
        return {"taskId": TASK, "status": "GENERATED_ONLY", "containerExecution": "NOT_RUN",
                "files": sorted(path.name for path in directory.iterdir()), "publicCertificateSha256": certificates}
    finally:
        os.umask(previous_umask)


def main():
    """命令行只接收私有目录；错误不打印秘密或外部工具原始诊断。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True,
                        help="全新本树 .tools/security/g4-m1-recovery-001-* 目录；生成后由 Master 审查挂载")
    arguments = parser.parse_args()
    try:
        print(json.dumps(generate(arguments.private_dir), ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as failure:
        print(json.dumps({"taskId": TASK, "status": "REFUSED", "category": type(failure).__name__,
                          "details": "SUPPRESSED", "partialPrivateFiles": "KEEP_FOR_EXACT_REVIEW"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
