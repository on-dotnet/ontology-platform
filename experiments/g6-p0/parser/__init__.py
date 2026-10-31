"""仅供 G6-P0 PREP 的标准库合成解析入口；不是正式产品 DTO。"""
from .core import (AnchorSegment, DEFAULT_CONFIG, DocumentIR, DocumentVersion, ParseArtifact,
                   ParserError, SourceAnchor, SourceMap, canonical, create_anchor, find_anchor,
                   ir_from_json, ir_to_json, parse_bytes, parse_file, validate_anchor, validate_ir)

__all__ = ['AnchorSegment', 'DEFAULT_CONFIG', 'DocumentIR', 'DocumentVersion', 'ParseArtifact',
           'ParserError', 'SourceAnchor', 'SourceMap', 'canonical', 'create_anchor', 'find_anchor',
           'ir_from_json', 'ir_to_json', 'parse_bytes', 'parse_file', 'validate_anchor', 'validate_ir']
