# Canonical 修复独立限定审查

Reviewer=slice_review，非作者只读，结论PASS可冻结并进入真实LinuxCI；无P1/P2。Jena6.2.0/JRE摘要/SHA512/依赖不变；HTTPS两固定源、有界180x2、坏hash不fallback、tar前verify、canonical外600均成立。CI冷构建前置、M2归属与后续reused=false拒绝成立。独立sh -n、PowerShell AST、context重算、限定diff-check exit0。

新shell5RED、allowlist专项RED及完整16GREEN已读。实际Mac cold/hit context=1e45f836d9837cbc75d23adb3ad37b0ff79a545ef06102a87aa246feea9cc1e5，image=sha256:39b0fb6616a466a05b2ff8c691bb14a63557c70118d433a4b70fd1068b1bef60，false→true，images10→11→11/history1→2→2。初次COPY遗漏helper的8.896秒失败保留；分类CHECKSUM_MISMATCH是BuildKit COPY输入，不是archive内容hash失败。已补.dockerignore owned_path和精确白名单。

官网https://jena.apache.org/download/直接列6.2.0 dlcdn，https://downloads.apache.org/jena/binaries/apache-jena-fuseki-6.2.0.tar.gz.sha512与原锁完全一致；Mac HEAD/Range仅网络诊断，非Linux吞吐证明。旧CI只可定位RUN，包含下载/校验/解压，不捏造其具体子步。Linux cold及同HeadCI尚待实际验证。

覆盖增量5158b78独立PASS：只测试/证据，24次编辑25PG修订、每步独立重读与四源/旧源、当前assessment及113/0skip成立。WEB文案1c98e05仅去M1标题及准确中文解释，保留原诊断/source/hash/shape，18相关测试及lint/typecheck/diff-check0。
