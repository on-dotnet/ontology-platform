#!/usr/bin/env python3
"""任务消费者和受控资源边界的真实正反回归。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ARTIFACTS = ROOT / 'artifacts/g4-m1-main-integration-001'


class HostBoundaryTests(unittest.TestCase):
    """观测开始前必须拒绝目录越界、历史身份和已存在的证据。"""

    def invoke(self, path, *args):
        """固定解释器和有界子进程，不运行默认长监测。"""
        return subprocess.run([sys.executable, '-B', str(HERE / 'host_continuity.py'),
                               'monitor', '--output', str(path), '--seconds', '1',
                               *args], cwd=ROOT, capture_output=True, text=True, timeout=5)

    def test_outside_and_traversal(self):
        """绝对树外路径和词法父目录穿越在观测前拒绝。"""
        for path in (ROOT / 'artifacts/foreign/monitor.jsonl', ARTIFACTS / '../escape.jsonl', ARTIFACTS):
            with self.subTest(path=str(path)):
                result = self.invoke(path)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('TASK_OUTPUT_BOUNDARY', result.stderr)

    def test_existing_output_and_summary(self):
        """现有原始证据与摘要均保持原字节。"""
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            path = Path(directory) / 'monitor.jsonl'
            for occupied in (path, path.with_suffix('.summary.json')):
                occupied.write_text('preserved\n')
                result = self.invoke(path)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('EXISTING', result.stderr)
                self.assertEqual(occupied.read_text(), 'preserved\n')
                occupied.unlink()

    def test_symbolic_link_and_invalid_duration(self):
        """悬空摘要链接和超出预算的时长不能启动监测。"""
        with tempfile.TemporaryDirectory(dir=ARTIFACTS) as directory:
            path = Path(directory) / 'monitor.jsonl'
            path.with_suffix('.summary.json').symlink_to(Path(directory) / 'missing')
            result = self.invoke(path)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('EXISTING_OR_UNSAFE_SUMMARY', result.stderr)
            path.with_suffix('.summary.json').unlink()
            result = self.invoke(path, '--seconds', '14401')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('BOUND_OR_EXISTING_OUTPUT', result.stderr)

    def test_foreign_task_cli_is_not_accepted(self):
        """禁止用传入旧任务身份改写监测归属。"""
        result = self.invoke(ARTIFACTS / 'unused.jsonl', '--task-id', 'G4-M1-RECOVERY-001')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unrecognized arguments', result.stderr)


if __name__ == '__main__':
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    unittest.main(verbosity=2)
