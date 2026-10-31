"""纯标准库合成解析：真实原字节是身份、坐标和反序列化的唯一依据。

不实现 OCR、模型、网络、插件、语义判断或发布。所有转换均可按代码点回源。
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import os
import re
import stat
from types import MappingProxyType


class ParserError(ValueError):
    """仅公开固定错误码，避免异常携带文档内容、路径或系统错误信息。"""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


DEFAULT_CONFIG = MappingProxyType(dict(strip_bom=True, normalize_newlines=True, unicode_normalization='NONE',
                      csv_dialect='RFC4180_SUBSET', max_bytes=1048576, max_codepoints=262144,
                      max_segments=128, max_cells=10000))


def _require(condition, code='INVALID_CONTRACT'):
    """边界断言不依赖可被解释器优化移除的 assert。"""
    if not condition:
        raise ParserError(code)


def _json_types(value):
    """拒绝浮点、非字符串键、代理对象及孤立 surrogate，不规范化 Unicode。"""
    if type(value) is dict:
        for key, item in value.items():
            _require(type(key) is str)
            _json_types(key)
            _json_types(item)
    elif type(value) is list:
        for item in value:
            _json_types(item)
    elif type(value) is str:
        try:
            value.encode('utf-8', errors='strict')
        except UnicodeError:
            raise ParserError('INVALID_CONTRACT') from None
    else:
        _require(value is None or type(value) in (bool, int))


def canonical(value):
    """冻结附录 A 的紧凑排序 JSON；此入口同时严格检查可接受的数据类型。"""
    try:
        _json_types(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, RecursionError, UnicodeError):
        raise ParserError('INVALID_CONTRACT') from None


def _hash(raw):
    """哈希输入始终为准确字节。"""
    return hashlib.sha256(raw).hexdigest()


def _integer(value, minimum=0, maximum=None):
    """Python bool 是 int 子类，故必须以精确类型拒绝布尔坐标和预算。"""
    _require(type(value) is int and value >= minimum and (maximum is None or value <= maximum))


def _string(value):
    """身份字符串必须非空且可用严格 UTF-8 表示；不执行 trim。"""
    _require(type(value) is str and bool(value))
    _json_types(value)


def _config(value):
    """仅允许完整冻结配置；预算可缩小，不能扩大或引入第三方选项。"""
    value = dict(DEFAULT_CONFIG) if value is None else value
    _require(type(value) is dict and set(value) == set(DEFAULT_CONFIG))
    for key, default in DEFAULT_CONFIG.items():
        if key.startswith('max_'):
            _integer(value[key], 1, default)
        else:
            _require(type(value[key]) is type(default) and value[key] == default)
    return dict(value)


def _scope(value):
    """scope 必须显式给出组织和已按 ordinal 排序去重的厂区身份。"""
    _require(type(value) is dict and set(value) == {'organization_id', 'site_ids'})
    _string(value['organization_id'])
    sites = value['site_ids']
    _require(type(sites) is list and bool(sites))
    for site in sites:
        _string(site)
    _require(sites == sorted(set(sites)))
    return {'organization_id': value['organization_id'], 'site_ids': list(sites)}


@dataclass
class DocumentVersion:
    """不可变输入的业务身份；验证时从原字节重新计算 version_id。"""
    document_id: str
    version_id: str
    version: int
    scope: dict
    format: str
    source_sha256: str
    size_bytes: int
    encoding: str = 'UTF-8'


@dataclass
class ParseArtifact:
    """解析器版本、配置、原件和实际映射共同绑定的派生身份。"""
    artifact_id: str
    document_version_id: str
    parser_name: str
    parser_version: str
    config_digest: str
    source_document_hash: str
    ir_schema_version: int
    source_map_hash: str


@dataclass
class SourceMap:
    """全局 lexical 文本和 CSV 逻辑 cell 均直接映射原件代码点半开区间。"""
    schema_version: int
    document_version_id: str
    source_document_hash: str
    global_spans: list
    cell_maps: list


@dataclass
class DocumentIR:
    """仅实验读模型；raw/config 用于重验，所有模式 graph_artifact 均为空。"""
    document_version: DocumentVersion
    parse_artifact: ParseArtifact
    text: str
    blocks: list
    cells: list
    source_map: SourceMap
    quality_signals: list
    mode: str
    graph_artifact: object
    raw: bytes
    config: dict


@dataclass
class AnchorSegment:
    """原件 byte/codepoint 与所选 IR 空间同时记录的非空半开区间。"""
    byte_start: int
    byte_end: int
    codepoint_start: int
    codepoint_end: int
    ir_start: int
    ir_end: int


@dataclass
class SourceAnchor:
    """不拥有页面/bbox 推测能力；EXACT 才具有文字高亮资格。"""
    document_version_id: str
    source_document_hash: str
    parse_artifact_id: str
    precision: str
    segments: list
    text_hash: str
    text_space: str = 'DOCUMENT'
    block: object = None
    page: object = None
    row: object = None
    column: object = None

    @property
    def highlight_eligible(self):
        """仅作为验证后的显示提示，消费者仍需先调用 validate_anchor。"""
        return self.precision == 'EXACT' and bool(self.segments)


def _normalize(source):
    """BOM 不进入 IR；CRLF 一个 LF 映射两个原件代码点，不做 Unicode 合并。"""
    chars, spans = [], []
    index = 1 if source.startswith('\ufeff') else 0
    while index < len(source):
        start = index
        char = source[index]
        index += 1
        if char == '\r':
            if index < len(source) and source[index] == '\n':
                index += 1
            char = '\n'
        chars.append(char)
        spans.append([start, index])
    return ''.join(chars), spans


def _csv_cells(text, global_spans, maximum):
    """严格 RFC4180 子集状态机，保留 lexical 全文并单独建立去引号 cell 映射。

    引号仅可出现在字段开头；闭引号后只允许分隔符/换行/EOF；列数必须一致。
    公式只添加到字符串，不求值。已规范化换行通过 global_spans 回到 CRLF。
    """
    if not text:
        return [], []
    cells, maps = [], []
    row = column = index = 0
    widths = []
    while index < len(text):
        chars, spans = [], []
        if text[index] == '"':
            index += 1
            closed = False
            while index < len(text):
                char = text[index]
                if char == '"':
                    if index + 1 < len(text) and text[index + 1] == '"':
                        chars.append('"')
                        spans.append([global_spans[index][0], global_spans[index + 1][1]])
                        index += 2
                    else:
                        index += 1
                        closed = True
                        break
                else:
                    chars.append(char)
                    spans.append(list(global_spans[index]))
                    index += 1
            _require(closed, 'INVALID_CSV')
            _require(index == len(text) or text[index] in ',\n', 'INVALID_CSV')
        else:
            while index < len(text) and text[index] not in ',\n':
                _require(text[index] != '"', 'INVALID_CSV')
                chars.append(text[index])
                spans.append(list(global_spans[index]))
                index += 1
        cells.append({'row': row, 'column': column, 'text': ''.join(chars),
                      'header_ref': None if row == 0 else {'row': 0, 'column': column}})
        maps.append({'row': row, 'column': column, 'spans': spans})
        _require(len(cells) <= maximum, 'LIMIT_EXCEEDED')
        if index == len(text):
            widths.append(column + 1)
            break
        delimiter = text[index]
        index += 1
        if delimiter == '\n':
            widths.append(column + 1)
            row += 1
            column = 0
        else:
            column += 1
            if index == len(text):
                cells.append({'row': row, 'column': column, 'text': '',
                              'header_ref': None if row == 0 else {'row': 0, 'column': column}})
                maps.append({'row': row, 'column': column, 'spans': []})
                _require(len(cells) <= maximum, 'LIMIT_EXCEEDED')
                widths.append(column + 1)
    _require(all(width == widths[0] for width in widths), 'INVALID_CSV')
    return cells, maps


def _blocks(text):
    """本批块只代表真实存在的规范化物理行，不制造页码或语义边界。"""
    result, start = [], 0
    for index, line in enumerate(text.splitlines(keepends=True)):
        end = start + len(line)
        result.append({'block_id': f'line-{index}', 'ir_start': start, 'ir_end': end, 'text': line})
        start = end
    return result


def parse_bytes(raw, *, document_id, version, scope, format, config=None, mode='DOCUMENT_ONLY'):
    """严格解码有界原字节并生成真实身份与映射，不读取业务时间或外部资源。"""
    _require(type(raw) is bytes)
    cfg = _config(config)
    _string(document_id)
    _integer(version, 1)
    scope = _scope(scope)
    _require(type(format) is str and format in ('TXT', 'MD', 'CSV'))
    _require(type(mode) is str and mode in ('DOCUMENT_ONLY', 'DISCOVERY', 'ONTOLOGY_GUIDED'))
    _require(len(raw) <= cfg['max_bytes'], 'LIMIT_EXCEEDED')
    try:
        source = raw.decode('utf-8', errors='strict')
    except UnicodeError:
        raise ParserError('INVALID_UTF8') from None
    _require(len(source) <= cfg['max_codepoints'], 'LIMIT_EXCEEDED')
    fields = dict(document_id=document_id, version=version, scope=scope, format=format,
                  encoding='UTF-8', source_sha256=_hash(raw), size_bytes=len(raw))
    version_id = 'dv-' + _hash(canonical(dict(schema_version=1, **fields)))
    dv = DocumentVersion(version_id=version_id, **fields)
    text, spans = _normalize(source)
    cells, cell_maps = _csv_cells(text, spans, cfg['max_cells']) if format == 'CSV' else ([], [])
    sm = SourceMap(1, version_id, dv.source_sha256, spans, cell_maps)
    map_hash = _hash(canonical(asdict(sm)))
    artifact_fields = dict(document_version_id=version_id, source_document_hash=dv.source_sha256,
                           parser_name='stdlib-synthetic', parser_version='1.0.0',
                           config_digest=_hash(canonical(cfg)), source_map_hash=map_hash, ir_schema_version=1)
    artifact_id = 'pa-' + _hash(canonical(dict(schema_version=1, **artifact_fields)))
    pa = ParseArtifact(artifact_id=artifact_id, **artifact_fields)
    return DocumentIR(dv, pa, text, _blocks(text), cells, sm, [], mode, None, raw, cfg)


def _export(ir):
    """JSON 不携带原字节；反序列化必须由调用者重新提供实际原件。"""
    return dict(schema_version=1, document_version=asdict(ir.document_version),
                parse_artifact=asdict(ir.parse_artifact), text=ir.text, blocks=ir.blocks,
                cells=ir.cells, source_map=asdict(ir.source_map), quality_signals=ir.quality_signals,
                mode=ir.mode, graph_artifact=ir.graph_artifact, config=ir.config)


def validate_ir(ir):
    """重新执行纯函数解析并逐字段对比 canonical 字节，拒绝自报 hash/map 互证。

    这也使 bool/整数、未知嵌套字段、伪造块、cell/header 和图产物无法混过比较。
    """
    _require(type(ir) is DocumentIR and type(ir.document_version) is DocumentVersion)
    dv = ir.document_version
    rebuilt = parse_bytes(ir.raw, document_id=dv.document_id, version=dv.version,
                          scope=dv.scope, format=dv.format, config=ir.config, mode=ir.mode)
    try:
        _require(canonical(_export(ir)) == canonical(_export(rebuilt)), 'BINDING_MISMATCH')
    except (TypeError, AttributeError):
        raise ParserError('INVALID_CONTRACT') from None
    return ir


def _space(ir, text_space, row, column):
    """CELL 逻辑空间不借助 find 反推位置；row/column 只接受真实 cell。"""
    _require(text_space in ('DOCUMENT', 'CELL'))
    if text_space == 'DOCUMENT':
        _require(row is None and column is None)
        return ir.text, ir.source_map.global_spans
    _integer(row)
    _integer(column)
    for cell, mapping in zip(ir.cells, ir.source_map.cell_maps):
        if cell['row'] == row and cell['column'] == column:
            return cell['text'], mapping['spans']
    raise ParserError('INVALID_CONTRACT')


def create_anchor(ir, ranges, *, precision='EXACT', text_space='DOCUMENT', row=None, column=None,
                  block=None, page=None):
    """由已重验映射创建锚点，半开区间有序不重叠，拼接片段计算文字 hash。"""
    validate_ir(ir)
    _require(type(ranges) in (list, tuple))
    _require(len(ranges) <= ir.config['max_segments'], 'LIMIT_EXCEEDED')
    _require(precision in ('EXACT', 'BLOCK', 'UNKNOWN') and page is None)
    text, mapping = _space(ir, text_space, row, column)
    segments, chunks = [], []
    if precision == 'EXACT':
        _require(bool(ranges))
        if block is not None:
            _require(text_space == 'DOCUMENT' and type(block) is str)
            blocks = [b for b in ir.blocks if b['block_id'] == block]
            _require(len(blocks) == 1)
        source = ir.raw.decode('utf-8')
        byte_offsets = [0]
        for char in source:
            byte_offsets.append(byte_offsets[-1] + len(char.encode('utf-8')))
        previous = 0
        for pair in ranges:
            _require(type(pair) in (list, tuple) and len(pair) == 2)
            start, end = pair
            _integer(start)
            _integer(end)
            _require(previous <= start < end <= len(text))
            if block is not None:
                _require(blocks[0]['ir_start'] <= start < end <= blocks[0]['ir_end'])
            cp_start, cp_end = mapping[start][0], mapping[end - 1][1]
            segments.append(AnchorSegment(byte_offsets[cp_start], byte_offsets[cp_end], cp_start, cp_end, start, end))
            chunks.append(text[start:end])
            previous = end
    else:
        _require(not ranges and text_space == 'DOCUMENT')
        if precision == 'BLOCK':
            _require(type(block) is str)
            found = [b for b in ir.blocks if b['block_id'] == block]
            _require(len(found) == 1)
            chunks.append(found[0]['text'])
        else:
            _require(block is None)
    return SourceAnchor(ir.document_version.version_id, ir.document_version.source_sha256,
                        ir.parse_artifact.artifact_id, precision, segments, _hash(''.join(chunks).encode('utf-8')),
                        text_space, block, page, row, column)


def validate_anchor(ir, anchor):
    """从 IR 与原件重新派生坐标，禁止旧版本/scope/config/artifact 借用锚点。"""
    _require(type(anchor) is SourceAnchor and type(anchor.segments) is list)
    _require(all(type(s) is AnchorSegment for s in anchor.segments))
    expected = create_anchor(ir, [(s.ir_start, s.ir_end) for s in anchor.segments],
                             precision=anchor.precision, text_space=anchor.text_space,
                             row=anchor.row, column=anchor.column, block=anchor.block, page=anchor.page)
    _require(canonical(asdict(anchor)) == canonical(asdict(expected)), 'BINDING_MISMATCH')
    return anchor


def find_anchor(ir, needle, *, occurrence=None, text_space='DOCUMENT', row=None, column=None):
    """重复匹配默认 AMBIGUOUS，显式 occurrence 从0开始且包含重叠匹配。"""
    validate_ir(ir)
    _string(needle)
    text, _ = _space(ir, text_space, row, column)
    starts, start = [], 0
    while True:
        index = text.find(needle, start)
        if index < 0:
            break
        starts.append(index)
        start = index + 1
    _require(bool(starts), 'NOT_FOUND')
    if occurrence is None:
        _require(len(starts) == 1, 'AMBIGUOUS')
        occurrence = 0
    _integer(occurrence)
    _require(occurrence < len(starts), 'NOT_FOUND')
    start = starts[occurrence]
    return create_anchor(ir, [(start, start + len(needle))], text_space=text_space, row=row, column=column)


def ir_to_json(ir):
    """只有重验通过的 IR 可导出带显式 schema_version 的 JSON。"""
    validate_ir(ir)
    return canonical(_export(ir)).decode('utf-8')


def _unique_pairs(pairs):
    """json.loads 默认接受重复键；身份合同必须显式拒绝。"""
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _invalid_number(value):
    """浮点、NaN 和 Infinity 不属于该实验 JSON 合同。"""
    raise ParserError('INVALID_CONTRACT')


def ir_from_json(serialized, raw):
    """不从自报坐标构造可信对象；按真实 raw/config 重建后严格比较所有字段。"""
    _require(type(serialized) is str)
    try:
        data = json.loads(serialized, object_pairs_hook=_unique_pairs,
                          parse_float=_invalid_number, parse_constant=_invalid_number)
        _json_types(data)
        _require(type(data) is dict)
        dv = data['document_version']
        expected = parse_bytes(raw, document_id=dv['document_id'], version=dv['version'], scope=dv['scope'],
                               format=dv['format'], config=data['config'], mode=data['mode'])
        _require(canonical(data) == canonical(_export(expected)), 'BINDING_MISMATCH')
        return expected
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        raise ParserError('INVALID_CONTRACT') from None


def _safe_platform():
    """缺少 nofollow/openat/fstat 等等价能力时明确拒绝，不降级成普通 open。"""
    return (os.name == 'posix' and hasattr(os, 'O_NOFOLLOW') and hasattr(os, 'O_DIRECTORY')
            and hasattr(os, 'O_NONBLOCK') and os.open in os.supports_dir_fd)


def parse_file(fixture_root, relative_path, *, document_id, version, scope, format,
               config=None, mode='DOCUMENT_ONLY'):
    """从固定根的描述符逐级 nofollow 打开，拒链接/FIFO，最多读取预算+1 字节。

    根自身和所有祖先也 nofollow；描述符固定目录对象，避免 resolve 后普通 open 的竞态。
    O_NONBLOCK 防止在 fstat 前被 FIFO 阻塞。所有成功打开的描述符在 finally 精确释放。
    """
    _require(_safe_platform(), 'NOT_SUPPORTED')
    cfg = _config(config)
    _require(type(relative_path) is str and bool(relative_path), 'UNSAFE_PATH')
    _require(not relative_path.startswith('/') and not re.search(r'[\\:\x00-\x1f\x7f]', relative_path), 'UNSAFE_PATH')
    components = relative_path.split('/')
    _require(all(part and part not in ('.', '..') for part in components), 'UNSAFE_PATH')
    try:
        root = os.fspath(fixture_root)
        _require(type(root) is str and os.path.isabs(root), 'UNSAFE_PATH')
        root.encode('utf-8', errors='strict')
        relative_path.encode('utf-8', errors='strict')
    except (TypeError, UnicodeError):
        raise ParserError('UNSAFE_PATH') from None
    _require(not re.search(r'[\x00-\x1f\x7f]', root), 'UNSAFE_PATH')
    root_parts = root.split('/')[1:]
    _require(all(part and part not in ('.', '..') for part in root_parts), 'UNSAFE_PATH')
    descriptors = []
    try:
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        current = os.open('/', directory_flags)
        descriptors.append(current)
        for part in root_parts + components[:-1]:
            current = os.open(part, directory_flags, dir_fd=current)
            descriptors.append(current)
            _require(stat.S_ISDIR(os.fstat(current).st_mode), 'NOT_REGULAR_FILE')
        fd = os.open(components[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
        descriptors.append(fd)
        before = os.fstat(fd)
        _require(stat.S_ISREG(before.st_mode), 'NOT_REGULAR_FILE')
        _require(before.st_size <= cfg['max_bytes'], 'LIMIT_EXCEEDED')
        chunks, remaining = [], cfg['max_bytes'] + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b''.join(chunks)
        _require(len(raw) <= cfg['max_bytes'], 'LIMIT_EXCEEDED')
        after = os.fstat(fd)
        _require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                 == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                 and len(raw) == after.st_size, 'SOURCE_CHANGED')
        return parse_bytes(raw, document_id=document_id, version=version, scope=scope, format=format,
                           config=cfg, mode=mode)
    except PermissionError:
        raise ParserError('PERMISSION_DENIED') from None
    except OSError:
        raise ParserError('READ_FAILED') from None
    finally:
        for fd in reversed(descriptors):
            os.close(fd)
