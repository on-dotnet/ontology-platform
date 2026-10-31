"""标准库合成合同正反例；所有临时资源仅属于本次测试。"""
import base64
import copy
import csv
import io
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from parser import (ParserError, DEFAULT_CONFIG, parse_bytes, parse_file, validate_ir,
                    create_anchor, find_anchor, validate_anchor, ir_to_json, ir_from_json, canonical)

SCOPE = {'organization_id': '合成组织', 'site_ids': ['A', 'B']}


def parse(raw=b'abc', **kw):
    """给所有合成输入提供显式业务身份，不读取文件时间。"""
    args = dict(document_id='synthetic', version=1, scope=copy.deepcopy(SCOPE), format='TXT')
    args.update(kw)
    return parse_bytes(raw, **args)


class ParserContractTests(unittest.TestCase):
    def reject(self, fn, code=None):
        with self.assertRaises(ParserError) as ctx:
            fn()
        if code:
            self.assertEqual(ctx.exception.code, code)
        self.assertRegex(str(ctx.exception), r'^[A-Z0-9_]+$')

    def test_unicode_bom_newlines_and_multisegment_roundtrip(self):
        raw = '\ufeff中😀e\u0301\r\n👩\u200d💻\r末\n'.encode()
        ir = parse(raw)
        self.assertEqual(ir.text, '中😀e\u0301\n👩\u200d💻\n末\n')
        self.assertEqual(ir.source_map.global_spans[4], [5, 7])
        a = create_anchor(ir, [(0, 4), (5, 8)])
        self.assertEqual(a.text_hash, hashlib.sha256('中😀e\u0301👩\u200d💻'.encode()).hexdigest())
        self.assertEqual(a.segments[0].byte_start, 3)
        self.assertEqual(a.segments[1].codepoint_start, 7)
        validate_anchor(ir, a)
        validate_ir(ir)

    def test_crlf_span_replays_two_source_codepoints(self):
        ir = parse(b'a\r\nb\rc\n')
        a = create_anchor(ir, [(1, 2)])
        self.assertEqual((a.segments[0].byte_start, a.segments[0].byte_end), (1, 3))
        self.assertEqual((a.segments[0].codepoint_start, a.segments[0].codepoint_end), (1, 3))

    def test_empty_document_valid_but_exact_empty_invalid(self):
        ir = parse(b'')
        self.assertEqual(ir.text, '')
        self.assertEqual(ir.blocks, [])
        self.reject(lambda: create_anchor(ir, [(0, 0)]))
        self.reject(lambda: create_anchor(ir, []))

    def test_bad_utf8_and_surrogates(self):
        for raw in [b'\xff', b'\xe4\xb8', b'\xed\xa0\x80']:
            with self.subTest(raw=raw):
                self.reject(lambda: parse(raw), 'INVALID_UTF8')
        self.reject(lambda: parse(b'a', document_id='\ud800'))

    def test_repeated_text_requires_occurrence(self):
        ir = parse('甲 甲 甲'.encode())
        self.reject(lambda: find_anchor(ir, '甲'), 'AMBIGUOUS')
        a = find_anchor(ir, '甲', occurrence=1)
        self.assertEqual(a.segments[0].ir_start, 2)
        self.reject(lambda: find_anchor(ir, '未出现'), 'NOT_FOUND')
        self.reject(lambda: find_anchor(ir, '甲', occurrence=True))

    def test_identity_scope_version_config_and_no_mtime(self):
        ir = parse()
        changed = [parse(version=2), parse(scope={'organization_id': '其他', 'site_ids':['A']}),
                   parse(document_id='different')]
        a = create_anchor(ir, [(0, 1)])
        for item in changed:
            self.assertNotEqual(ir.document_version.version_id, item.document_version.version_id)
            self.reject(lambda: validate_anchor(item, a))
        cfg = dict(DEFAULT_CONFIG, max_bytes=100)
        other = parse(config=cfg)
        self.assertNotEqual(other.parse_artifact.artifact_id, ir.parse_artifact.artifact_id)
        self.reject(lambda: validate_anchor(other, a))
        self.assertFalse(hasattr(ir.document_version, 'mtime'))

    def test_exact_canonical_identity(self):
        ir = parse()
        d = ir_to_json(ir)
        obj = json.loads(d)['document_version']
        version_id = obj.pop('version_id')
        obj['schema_version'] = 1
        canonical = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        self.assertEqual(version_id, 'dv-' + hashlib.sha256(canonical).hexdigest())

    def test_scope_and_integer_validation(self):
        for version in [True, 0, -1, 1.0, '1']:
            self.reject(lambda: parse(version=version))
        for scope in [{}, {'organization_id':'x','site_ids':[]}, {'organization_id':'x','site_ids':['B','A']},
                      {'organization_id':'x','site_ids':['A','A']}, dict(SCOPE, unknown=1)]:
            self.reject(lambda: parse(scope=scope))
        self.reject(lambda: parse(format='PDF'))
        self.reject(lambda: parse(mode='EXECUTE'))

    def test_config_unknown_bool_float_nan_and_limits(self):
        for kw in [{'unknown':1}, {'max_bytes':True}, {'max_segments':1.0}, {'max_cells':0},
                   {'max_bytes':1048577}, {'strip_bom':False}, {'unicode_normalization':'NFC'}, {'max_bytes':float('nan')}]:
            cfg = dict(DEFAULT_CONFIG, **kw)
            self.reject(lambda: parse(config=cfg))
        self.reject(lambda: parse(b'ab', config=dict(DEFAULT_CONFIG, max_bytes=1)), 'LIMIT_EXCEEDED')
        self.reject(lambda: parse('中文'.encode(), config=dict(DEFAULT_CONFIG, max_codepoints=1)), 'LIMIT_EXCEEDED')
        ir = parse(b'abc', config=dict(DEFAULT_CONFIG, max_segments=1))
        self.reject(lambda: create_anchor(ir, [(0,1), (2,3)]), 'LIMIT_EXCEEDED')

    def test_anchor_ranges_order_overlap_bounds_and_bool(self):
        ir = parse()
        for ranges in [[(-1,1)], [(0,4)], [(2,1)], [(0,0)], [(1,2),(0,1)], [(0,2),(1,3)], [(False,1)]]:
            self.reject(lambda: create_anchor(ir, ranges))

    def test_tampered_map_text_raw_identity_rejected(self):
        for mutate in [lambda x: x.source_map.global_spans.__setitem__(0,[1,2]),
                       lambda x: setattr(x,'text','xyz'), lambda x: setattr(x,'raw',b'xyz'),
                       lambda x: setattr(x.document_version,'source_sha256','0'*64),
                       lambda x: setattr(x.document_version,'version_id','dv-'+'0'*64),
                       lambda x: setattr(x.parse_artifact,'artifact_id','pa-'+'0'*64),
                       lambda x: setattr(x.parse_artifact,'config_digest','0'*64),
                       lambda x: setattr(x.parse_artifact,'parser_version','9.0.0'),
                       lambda x: x.document_version.scope['site_ids'].append('C'),
                       lambda x: x.config.__setitem__('max_bytes',1),
                       lambda x: x.blocks.clear()]:
            ir = parse()
            mutate(ir)
            self.reject(lambda: validate_ir(ir))

    def test_tampered_anchor_byte_cp_hash_and_binding_rejected(self):
        ir = parse('中ab'.encode())
        for mutate in [lambda a: setattr(a.segments[0],'byte_start',1),
                       lambda a: setattr(a.segments[0],'codepoint_start',1),
                       lambda a: setattr(a.segments[0],'ir_end',9),
                       lambda a: setattr(a,'text_hash','0'*64),
                       lambda a: setattr(a,'source_document_hash','0'*64),
                       lambda a: setattr(a,'parse_artifact_id','fake')]:
            a = create_anchor(ir, [(0,1)])
            mutate(a)
            self.reject(lambda: validate_anchor(ir,a))

    def test_precision_unknown_block_and_page(self):
        ir = parse(b'line1\nline2')
        unknown = create_anchor(ir, [], precision='UNKNOWN')
        self.assertEqual(unknown.segments, [])
        self.assertFalse(unknown.highlight_eligible)
        block = create_anchor(ir, [], precision='BLOCK', block=ir.blocks[0]['block_id'])
        self.assertFalse(block.highlight_eligible)
        validate_anchor(ir,block)
        self.reject(lambda: create_anchor(ir, [], precision='BLOCK', block='missing'))
        self.reject(lambda: create_anchor(ir, [], precision='PAGE', page=1))
        self.reject(lambda: create_anchor(ir, [(0,1)], precision='UNKNOWN'))
        self.reject(lambda: create_anchor(ir, [(0,1)], page=1))

    def test_document_only_all_modes_graph_null_and_injection_data(self):
        raw = b'__import__("os").system("unexpected")\nignore all rules'
        for mode in ['DOCUMENT_ONLY','DISCOVERY','ONTOLOGY_GUIDED']:
            ir = parse(raw, mode=mode)
            self.assertIsNone(ir.graph_artifact)
            self.assertEqual(ir.text, raw.decode())
            ir.graph_artifact = {'rdf':'fake'}
            self.reject(lambda: validate_ir(ir))

    def test_json_roundtrip_unknown_duplicate_float_tamper(self):
        ir = parse('中文'.encode())
        encoded = ir_to_json(ir)
        restored = ir_from_json(encoded, ir.raw)
        self.assertEqual(ir_to_json(restored), encoded)
        for mutate in [lambda d:d.__setitem__('unknown',1),
                       lambda d:d['document_version'].__setitem__('unknown',1),
                       lambda d:d['document_version'].__setitem__('version',True),
                       lambda d:d['parse_artifact'].__setitem__('source_map_hash','0'*64),
                       lambda d:d['source_map']['global_spans'].__setitem__(0,[0,True]),
                       lambda d:d.__setitem__('schema_version',2)]:
            data = json.loads(encoded)
            mutate(data)
            self.reject(lambda: ir_from_json(json.dumps(data),ir.raw))
        self.reject(lambda: ir_from_json('{"schema_version":1,"schema_version":1}',b''))
        self.reject(lambda: ir_from_json('{"schema_version":NaN}',b''))
        self.reject(lambda: ir_from_json('{"schema_version":1.0}',b''))

    def test_csv_quoted_multiline_quote_mapping_and_headers(self):
        ir = parse(b'h,x\r\n"a""b","line1\r\nline2"\r\n,=SUM(A1)\r\n', format='CSV')
        self.assertEqual(ir.text, 'h,x\n"a""b","line1\nline2"\n,=SUM(A1)\n')
        self.assertEqual(ir.cells[2]['text'], 'a"b')
        self.assertEqual(ir.cells[2]['header_ref'], {'row':0,'column':0})
        self.assertIsNone(ir.cells[0]['header_ref'])
        self.assertEqual(ir.cells[4]['text'], '')
        self.assertEqual(ir.cells[5]['text'], '=SUM(A1)')
        a = create_anchor(ir, [(1,2)], text_space='CELL', row=1,column=0)
        seg = a.segments[0]
        self.assertEqual(ir.raw[seg.byte_start:seg.byte_end],b'""')
        self.assertEqual(a.text_hash,hashlib.sha256(b'"').hexdigest())
        validate_anchor(ir,a)
        self.reject(lambda: create_anchor(ir, [(0,1)], text_space='CELL',row=2,column=0))
        self.reject(lambda: create_anchor(ir, [(0,1)],row=1,column=0))

    def test_csv_contract_appendix_example(self):
        ir = parse(b'h\r\n"a""b"\r\n',format='CSV')
        self.assertEqual(ir.source_map.cell_maps[1]['spans'],[[4,5],[5,7],[7,8]])
        a = create_anchor(ir,[(0,3)],text_space='CELL',row=1,column=0)
        self.assertEqual((a.segments[0].codepoint_start,a.segments[0].codepoint_end),(4,8))
        self.assertEqual(a.text_hash,hashlib.sha256(b'a"b').hexdigest())

    def test_bad_csv_and_cell_limits(self):
        for raw in [b'a,b\n1', b'a\n"unclosed', b'a\n"x"garbage', b'a\nx"y', b'a,b\n1,2,3']:
            self.reject(lambda: parse(raw,format='CSV'),'INVALID_CSV')
        self.reject(lambda: parse(b'a,b',format='CSV',config=dict(DEFAULT_CONFIG,max_cells=1)), 'LIMIT_EXCEEDED')
        self.assertEqual(len(parse(b'a,b\n1,\n',format='CSV').cells),4)

    def test_independent_artifact_and_map_canonical_hash(self):
        ir = parse(b'h\r\n"a""b"\r\n', format='CSV')
        def h(value):
            return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                             separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        dv = ir.document_version
        expected_map = dict(schema_version=1, document_version_id=dv.version_id,
                            source_document_hash=hashlib.sha256(ir.raw).hexdigest(),
                            global_spans=[[0,1],[1,3],[3,4],[4,5],[5,6],[6,7],[7,8],[8,9],[9,11]],
                            cell_maps=[{'row':0,'column':0,'spans':[[0,1]]},
                                       {'row':1,'column':0,'spans':[[4,5],[5,7],[7,8]]}])
        self.assertEqual(ir.parse_artifact.source_map_hash,h(expected_map))
        artifact = dict(schema_version=1, document_version_id=dv.version_id,
                        source_document_hash=hashlib.sha256(ir.raw).hexdigest(),
                        parser_name='stdlib-synthetic', parser_version='1.0.0',
                        config_digest=h(dict(DEFAULT_CONFIG)), source_map_hash=h(expected_map), ir_schema_version=1)
        self.assertEqual(ir.parse_artifact.artifact_id,'pa-'+h(artifact))

    def test_generated_csv_matrix_matches_stdlib_and_replays_cells(self):
        matrix = [['列一','列二','列三'],['中😀','e\u0301','👩\u200d💻'],
                  ['a,b','say "yes"','first\nsecond'],['','=1+1','repeat repeat']]
        output = io.StringIO(newline='')
        csv.writer(output,lineterminator='\r\n').writerows(matrix)
        raw = output.getvalue().encode()
        ir = parse(raw,format='CSV')
        self.assertEqual([c['text'] for c in ir.cells],[s for row in matrix for s in row])
        self.assertEqual(list(csv.reader(io.StringIO(ir.text,newline=''))),matrix)
        for cell in ir.cells:
            if not cell['text']:
                continue
            a = create_anchor(ir,[(0,len(cell['text']))],text_space='CELL',row=cell['row'],column=cell['column'])
            validate_anchor(ir,a)
            seg = a.segments[0]
            source = raw[seg.byte_start:seg.byte_end].decode().replace('\r\n','\n').replace('""','"')
            self.assertEqual(source,cell['text'])
        changed = copy.deepcopy(ir)
        changed.source_map.cell_maps[3]['spans'][0] = [0,1]
        self.reject(lambda: validate_ir(changed))

    def test_serialized_fixture_vectors(self):
        vectors = json.loads((ROOT/'fixtures'/'edge-cases.json').read_text())
        for item in vectors['cases']:
            raw = base64.b64decode(item['raw_base64'], validate=True)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),item['sha256'])
            if 'error' in item:
                self.reject(lambda: parse(raw,format=item['format']),item['error'])
            else:
                ir = parse(raw,format=item['format'])
                self.assertEqual(ir.text,item['text'])
                validate_ir(ir)

    def test_invalid_json_numbers_cycles_and_surrogates_have_safe_codes(self):
        self.reject(lambda: ir_from_json('{"version":'+'9'*5000+'}', b''))
        self.reject(lambda: ir_from_json('{"value":"\\ud800"}', b''))
        cycle = []
        cycle.append(cycle)
        self.reject(lambda: canonical(cycle))
        self.reject(lambda: parse(config=dict(DEFAULT_CONFIG,max_bytes=cycle)))

    def test_default_budget_cannot_be_mutated(self):
        with self.assertRaises(TypeError):
            DEFAULT_CONFIG['max_bytes'] = 10**9

    def test_seed_byte_copy_and_all_eighteen_anchor_spans(self):
        root = ROOT/'fixtures'/'synthetic_seed'
        manifest = json.loads((root/'seed-manifest.json').read_text())
        count = 0
        for item in manifest['documents']:
            raw = (root/item['file']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),item['sha256'])
            ir = parse(raw,format=Path(item['file']).suffix[1:].upper(),document_id=item['file'])
            for s in item['sourceSpans']:
                a = create_anchor(ir,[(s['startCodepoint'],s['endCodepoint'])])
                validate_anchor(ir,a)
                seg = a.segments[0]
                self.assertEqual(raw[seg.byte_start:seg.byte_end].decode(),s['text'])
                count += 1
        self.assertEqual(count,18)


class SafeFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='g6-p0-parser-prep-')
        self.addCleanup(self.cleanup_temp)
        self.root = Path(self.temp.name).resolve()
        (self.root/'good.txt').write_bytes(b'synthetic')

    def cleanup_temp(self):
        """对准确本次临时目录执行真实清理，并断言文件/链接/FIFO 均已消失。"""
        self.temp.cleanup()
        self.assertFalse(Path(self.temp.name).exists())

    def load(self,path,**kw):
        return parse_file(self.root,path,document_id='safe',version=1,scope=SCOPE,format='TXT',**kw)

    def reject(self,path,code=None,**kw):
        with self.assertRaises(ParserError) as ctx:
            self.load(path,**kw)
        if code:
            self.assertEqual(ctx.exception.code,code)
        self.assertRegex(str(ctx.exception),r'^[A-Z0-9_]+$')

    def test_ordinary_file_and_nested_file(self):
        self.assertEqual(self.load('good.txt').raw,b'synthetic')
        (self.root/'nested').mkdir()
        (self.root/'nested'/'good').write_bytes(b'x')
        self.assertEqual(self.load('nested/good').text,'x')

    def test_path_traversal_absolute_url_windows_empty(self):
        for path in ['../good.txt',str(self.root/'good.txt'),'a/../good','a\\b','C:foo','https://x','', '.', 'a//b', '\ud800', 'a\x00b']:
            self.reject(path,'UNSAFE_PATH')

    def test_invalid_root_types_and_encoding_are_safe(self):
        for root in [None, 42, '/synthetic/\ud800', '/synthetic/\x00']:
            with self.assertRaises(ParserError) as ctx:
                parse_file(root,'good.txt',document_id='x',version=1,scope=SCOPE,format='TXT')
            self.assertEqual(str(ctx.exception),'UNSAFE_PATH')

    def test_file_and_ancestor_symlinks_root_symlink(self):
        (self.root/'link').symlink_to(self.root/'good.txt')
        (self.root/'linked').symlink_to(self.root,target_is_directory=True)
        self.reject('link')
        self.reject('linked/good.txt')
        with self.assertRaises(ParserError):
            parse_file(self.root/'linked','good.txt',document_id='x',version=1,scope=SCOPE,format='TXT')

    def test_fifo_directory_and_bounded_read(self):
        (self.root/'folder').mkdir()
        os.mkfifo(self.root/'pipe')
        self.reject('folder','NOT_REGULAR_FILE')
        self.reject('pipe','NOT_REGULAR_FILE')
        self.reject('good.txt','LIMIT_EXCEEDED',config=dict(DEFAULT_CONFIG,max_bytes=2))

    def test_real_permission_denial_and_injected_oserror_safe(self):
        path = self.root/'good.txt'
        path.chmod(0)
        try:
            if os.geteuid() == 0:
                self.skipTest('root bypasses POSIX permissions; separate injection test remains')
            self.reject('good.txt','PERMISSION_DENIED')
        finally:
            path.chmod(0o600)

    def test_injected_permission_error_does_not_disclose(self):
        with patch('parser.core._safe_platform', return_value=True), patch('parser.core.os.open',side_effect=PermissionError('sensitive synthetic path/content')):
            self.reject('good.txt','PERMISSION_DENIED')

    def test_final_component_replaced_by_symlink_is_refused(self):
        original = os.open
        def raced_open(path, flags, *args, **kw):
            if path == 'good.txt':
                (self.root/'good.txt').unlink()
                (self.root/'good.txt').symlink_to(self.root/'other')
            return original(path,flags,*args,**kw)
        (self.root/'other').write_bytes(b'other synthetic data')
        with patch('parser.core._safe_platform',return_value=True), patch('parser.core.os.open',side_effect=raced_open):
            self.reject('good.txt','READ_FAILED')

    def test_file_growth_remains_bounded_to_budget_plus_one(self):
        path = self.root/'good.txt'
        path.write_bytes(b'x')
        original = os.read
        requests = []
        def growing_read(fd, count):
            requests.append(count)
            with path.open('ab') as stream:
                stream.write(b'yyyy')
            return original(fd,count)
        with patch('parser.core.os.read',side_effect=growing_read):
            self.reject('good.txt','LIMIT_EXCEEDED',config=dict(DEFAULT_CONFIG,max_bytes=2))
        self.assertEqual(requests,[3])

    def test_descriptors_closed_after_success_and_mid_walk_failure(self):
        original = os.open
        for name in ['good.txt','missing/sub/file']:
            descriptors = []
            def record_open(*args,**kw):
                fd = original(*args,**kw)
                descriptors.append(fd)
                return fd
            with patch('parser.core._safe_platform',return_value=True), patch('parser.core.os.open',side_effect=record_open):
                if name == 'good.txt':
                    self.load(name)
                else:
                    self.reject(name,'READ_FAILED')
            self.assertGreater(len(descriptors),0)
            for fd in descriptors:
                with self.assertRaises(OSError):
                    os.fstat(fd)

    def test_missing_file_and_no_safe_platform(self):
        self.reject('missing','READ_FAILED')
        with patch('parser.core._safe_platform',return_value=False):
            self.reject('good.txt','NOT_SUPPORTED')


if __name__ == '__main__':
    unittest.main()
