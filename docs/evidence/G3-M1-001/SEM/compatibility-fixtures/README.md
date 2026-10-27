# 实际V1/V2 manifest无损字节夹具

原始manifest JSON没有末尾LF，不能直接作为仓库文本文件提交；直接追加LF会改变真实对象hash。现在以带LF的base64 JSON封套存储，原始大小/hash不变，provenance同时核对封套和原始字节。没有重新序列化或修改实际manifest。

在仓库根目录恢复到一个新的空目录：

```sh
python3 docs/evidence/G3-M1-001/SEM/compatibility-fixtures/restore-manifests.py --output /private/tmp/g3-sem-restored-manifests
```

恢复器拒绝覆盖已存在文件，解码后逐字节重读并核对原始大小/hash。独立兼容读取二进制应读取恢复后的real-v1-manifest.json和real-v2-manifest.json，不读取封套作为manifest。真实业务无需重跑；本变更只纠正审查证据容器格式。
