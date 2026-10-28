# 当前任务日志文本规范化

仅转换终端CR换行及尾空白，不改命令、结果或失败事实。WEB原件可从独立树原提交 c209610 / ed55e0b 的准确Git对象恢复；Master原件保留 /private/tmp/g3-m3-direct-next-build.txt 和 /private/tmp/g3-m3-pnpm-build-after-direct.txt。首次集成SelfTest因文本格式失败日志保留。

- `docs/evidence/G3-M3-001/master/direct-next-build.txt` 原始SHA256 `a8b8f3167dd8f1c585141a14bda85704febee16ad9bdf7325b9f330ec6d67a41`，规范化SHA256 `ed7fae79c8dac7e2f02b379186902fd66b269356b84027af9566882172c7efca`。
- `docs/evidence/G3-M3-001/master/pnpm-build-after-direct.txt` 原始SHA256 `e05ee60c4b2f8ab7efa8bf1e2f47d2aa23bffb1187174a722971f124afbf29a8`，规范化SHA256 `217f96c06ea496aee78791235eef55f04a12270d84ca08d27d672760fc8f696f`。
- `docs/evidence/G3-M3-001/WEB/build-final.txt` 原始SHA256 `12b8188828131d919d50f18cafb3614d9d0a8b53f0b4da0b84cc55d5b3a31895`，规范化SHA256 `ea0b04c7a28db491c1cb515a679c926725a16a4803446dd2628617175b7df88f`。
- `docs/evidence/G3-M3-001/WEB/build.txt` 原始SHA256 `6b83a65e5b79d4d675b187d183094aa18d920a403407c5cfc118e1a7e9f5605f`，规范化SHA256 `abc6d72f1c4cf03c093c688ee73a77c3d3d64a34e58775f76fd238e770e39865`。
