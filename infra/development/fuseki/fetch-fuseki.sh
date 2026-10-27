#!/bin/sh
# 仅由唯一Dockerfile传入已冻结版本、SHA512与容器临时目标；不读取环境凭证。
set -eu
version=$1
expected_sha512=$2
destination=$3
primary="https://dlcdn.apache.org/jena/binaries/apache-jena-fuseki-${version}.tar.gz"
fallback="https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-${version}.tar.gz"

# 两次传输最多360秒，外层canonical构建仍为600秒；成功下载后散列不符立即退出。
if ! curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
    --max-redirs 3 --connect-timeout 15 --max-time 180 --retry 0 --output "$destination" "$primary"; then
    curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
        --max-redirs 3 --connect-timeout 15 --max-time 180 --retry 0 --output "$destination" "$fallback"
fi
printf '%s  %s\n' "$expected_sha512" "$destination" | sha512sum --check --strict
