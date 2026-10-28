#!/bin/sh
# 仅由唯一Dockerfile传入已冻结版本、SHA512与容器临时目标；不读取环境凭证。
set -eu
version=$1
expected_sha512=$2
destination=$3
primary="https://dlcdn.apache.org/jena/binaries/apache-jena-fuseki-${version}.tar.gz"
fallback="https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-${version}.tar.gz"

# Linux使用纳秒墙钟，BSD测试环境回退秒分辨率；只输出实际测得的毫秒数。
now_ms() {
    measured=$(date +%s%N)
    case "$measured" in *[!0-9]*) measured=$(($(date +%s) * 1000));; *) measured=$((measured / 1000000));; esac
    printf '%s\n' "$measured"
}
report_stage() {
    elapsed=$(($(now_ms) - started))
    [ "$elapsed" -ge 0 ] || elapsed=0
    printf 'CANONICAL_STAGE {"stage":"%s","durationMs":%s,"outcome":"%s","errorCategory":%s}\n' "$1" "$elapsed" "$2" "$3"
}

# 两次传输最多360秒，外层canonical构建仍为600秒；成功下载后散列不符立即退出。
started=$(now_ms)
if curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
    --max-redirs 3 --connect-timeout 15 --max-time 180 --retry 0 --output "$destination" "$primary"; then
    report_stage network PASS null
else
    primary_exit=$?
    case "$primary_exit" in 28) category='"NETWORK_TIMEOUT"';; 22) category='"DOWNLOAD_HTTP_FAILURE"';; *) category='"NETWORK_CONNECT"';; esac
    report_stage network FAIL "$category"
    started=$(now_ms)
    if curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
        --max-redirs 3 --connect-timeout 15 --max-time 180 --retry 0 --output "$destination" "$fallback"; then
        report_stage network PASS null
    else
        fallback_exit=$?
        case "$fallback_exit" in 28) category='"NETWORK_TIMEOUT"';; 22) category='"DOWNLOAD_HTTP_FAILURE"';; *) category='"NETWORK_CONNECT"';; esac
        report_stage network FAIL "$category"
        exit "$fallback_exit"
    fi
fi
started=$(now_ms)
if printf '%s  %s\n' "$expected_sha512" "$destination" | sha512sum --check --strict; then
    report_stage checksum PASS null
else
    report_stage checksum FAIL '"CHECKSUM_MISMATCH"'
    exit 1
fi
