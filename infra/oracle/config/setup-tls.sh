#!/bin/bash
# 仅在本任务合成源容器内执行；私钥不离开源数据卷。
set -euo pipefail
umask 077
base=/opt/oracle/oradata/g4-tls
mkdir -p "$base"
if [ -e "$base/ca.key" ]; then
  echo 'TLS material already exists; refusing overwrite' >&2
  exit 2
fi
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 30 -subj '/CN=G4 Oracle Development CA' -keyout "$base/ca.key" -out "$base/ca.crt" >/dev/null 2>&1
openssl req -newkey rsa:2048 -nodes -sha256 -subj '/CN=oracle-source' -keyout "$base/client.key" -out "$base/server.csr" >/dev/null 2>&1
cat > "$base/server.ext" <<'EXT'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:oracle-source
EXT
openssl x509 -req -in "$base/server.csr" -CA "$base/ca.crt" -CAkey "$base/ca.key" -CAcreateserial -out "$base/cert.crt" -days 7 -sha256 -extfile "$base/server.ext" >/dev/null 2>&1
TCPS_CERTS_LOCATION="$base" TCPS_PORT=2484 /opt/oracle/scripts/base/configTcps.sh
