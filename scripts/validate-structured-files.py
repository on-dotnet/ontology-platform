"""解析仓库YAML/TOML；不执行YAML对象构造、不读取忽略的凭证和工具缓存。"""

import argparse
import os
import pathlib
import sys
import tomllib

import yaml


SKIPPED = {".git", ".tools", ".worktrees", "artifacts", "node_modules", "bin", "obj", ".next", ".turbo"}


def validate(root: pathlib.Path) -> int:
    """仅语法检查，不将合法配置视为运行兼容或全面安全保证。"""
    count = 0
    for directory, subdirs, files in os.walk(root, followlinks=False):
        subdirs[:] = [name for name in subdirs if name not in SKIPPED and not (pathlib.Path(directory) / name).is_symlink()]
        for name in files:
            path = pathlib.Path(directory) / name
            if path.suffix not in {".toml", ".yaml", ".yml"} or path.is_symlink():
                continue
            relative = path.relative_to(root)
            try:
                if path.stat().st_size > 2 * 1024 * 1024:
                    raise ValueError("configuration too large")
                text = path.read_text(encoding="utf-8")
                if path.suffix == ".toml":
                    tomllib.loads(text)
                else:
                    list(yaml.safe_load_all(text))
                count += 1
            except (ValueError, UnicodeError, yaml.YAMLError) as exc:
                # 不打印解析器可能附带的敏感行；只给类型及相对路径。
                print(f"FAIL: structured syntax {relative} ({type(exc).__name__})")
                return 1
    print(f"PASS: YAML/TOML syntax, {count} files; runtime compatibility not implied.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=pathlib.Path)
    arguments = parser.parse_args()
    sys.exit(validate(arguments.root.resolve()))
