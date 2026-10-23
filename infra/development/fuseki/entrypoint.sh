#!/bin/sh
# 新卷及已有开发卷都需要明确创建TDB2目录；以非root身份执行。
set -eu
mkdir -p /fuseki/databases/ontology
exec /opt/fuseki/fuseki-server "$@"
