# G6-P0 Parser PREP

仅 Python 标准库、合成 TXT/MD/CSV 实验，不是正式 DTO、OCR/Docling、ACL 服务或本体发布。
`core.py` 实现冻结 `../contracts/parser-contract.md` 的身份和坐标算法。

从文件绝对位置将 `experiments/g6-p0` 加入 `sys.path` 后使用：

```python
from parser import parse_bytes, create_anchor, validate_anchor

ir = parse_bytes('合成文档'.encode('utf-8'), document_id='synthetic-1', version=1,
                 scope={'organization_id': 'synthetic-org', 'site_ids': ['A']}, format='TXT')
anchor = create_anchor(ir, [(0, 2)])
validate_anchor(ir, anchor)
```

`parse_file(root, relative_path, ...)` 使用同样的显式身份参数。root 必须为绝对的无链接目录路径；其全部祖先也逐级 nofollow 打开。调用者可以在可信配置阶段指定真实根；函数本身不 resolve 后降级普通 open。缺 POSIX 等价能力返回 `NOT_SUPPORTED`。Windows 实跑 NOT_RUN。

`DocumentIR.raw` 保留准确输入 bytes；`config` 为完整冻结配置，`DEFAULT_CONFIG` 只读。坐标是 Unicode codepoint 和 UTF-8 bytes，均为半开区间。原件 BOM 保留，IR 移除 BOM，CR/CRLF 变 LF，不执行 Unicode 合并、trim 或公式。CSV `ir.text` 保留 lexical 标点，`cells` 为逻辑字段，`source_map.cell_maps` 直接回源。CELL 锚点传 `text_space='CELL', row=..., column=...`；occurrence 从 0 开始。

数据类是可检测篡改的实验载体，不应把手工构造或修改后的对象直接当可信结果；使用前调用 `validate_ir` / `validate_anchor`。验证会从真实 raw/config 重新解析并比较全部 canonical 字段。`ir_to_json` 先验证；`ir_from_json(serialized, raw)` 必须提供实际 raw，重建全部身份/map，再比较 JSON；拒绝未知字段、重复键、浮点、bool 整数和伪造 hash。JSON 不打包 raw，无网络、插件或代码执行。

`UNKNOWN` 无坐标；`BLOCK` 仅可引用真实物理行块，二者均不可高亮；本批 `PAGE` 与所有页码/bbox 推测拒绝。EXACT 的多段区间严格有序不重叠，文本 hash 为所选空间各段文字的明确拼接；每次使用均重新绑定原件、scope、版本、解析配置和 artifact。

恢复与验证：

```sh
python3 -B -m unittest discover -s experiments/g6-p0/tests -p 'test_*.py' -v
python3 -B experiments/g6-p0/fixtures/synthetic_seed/verify_seed.py
```

35 个测试包括原 9 seed / 18 spans、独立 canonical hash、附录 B、标准库 csv 对照、真实 chmod 权限拒绝、路径/祖先/文件链接/FIFO、换链竞态、有界增长读取与描述符释放。每个安全文件测试生成自己的 `TemporaryDirectory`，清理回调实际删除后断言路径不存在。没有创建 Docker/模型/包/外部资源。
