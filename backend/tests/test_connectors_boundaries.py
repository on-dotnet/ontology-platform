"""Only `connectors` talks to external data sources (spec 003, 5.3, first barrier; section 15,
"外部数据源只读" ⑤).

The scan reads the source of every other module: none may import a database driver or open its
own engine, and the modules that work with external data (query, mcp, and the AI binding
suggestions) may not write SQL text either. They build `SelectQuery` values and call
`connectors.service` instead.
"""

import ast
import importlib
import re
from pathlib import Path

import pytest

PACKAGE = "ontology_platform.modules"
ROOT = Path(importlib.import_module(PACKAGE).__path__[0])
DRIVERS = ("psycopg", "psycopg2", "asyncpg", "pg8000", "sqlite3", "oracledb", "pymysql")
ENGINE_CALLS = {"create_engine", "create_async_engine", "exec_driver_sql", "connect"}
TEXT_CALLS = {"text", "literal_column", "TextClause"}
SQL_LITERAL = re.compile(
    r"\b(select\b.+\bfrom|insert\s+into|update\s+\S+\s+set|delete\s+from|drop\s+table|"
    r"create\s+table|alter\s+table|truncate\s)\b",
    re.IGNORECASE | re.DOTALL,
)


def _files_outside_connectors() -> list[Path]:
    return [path for path in sorted(ROOT.rglob("*.py")) if path.relative_to(ROOT).parts[0] != "connectors"]


def _external_data_files() -> list[Path]:
    files = [*sorted((ROOT / "query").rglob("*.py")), *sorted((ROOT / "mcp").rglob("*.py"))]
    files += sorted((ROOT / "ai").glob("binding_*.py"))
    return files


def driver_uses(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names if alias.name.split(".")[0] in DRIVERS]
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in DRIVERS:
            found.append(node.module or "")
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("sqlalchemy"):
            found += [
                f"{node.module}.{alias.name}"
                for alias in node.names
                if alias.name in ENGINE_CALLS - {"connect"}
            ]
        elif isinstance(node, ast.Attribute) and node.attr in ENGINE_CALLS - {"connect"}:
            found.append(node.attr)
    return found


def sql_text_uses(source: str) -> list[str]:
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sqlalchemy"):
            found += [alias.name for alias in node.names if alias.name in TEXT_CALLS]
        elif isinstance(node, ast.Attribute) and node.attr in TEXT_CALLS - {"text"}:
            found.append(node.attr)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and SQL_LITERAL.search(node.value)
        ):
            found.append(node.value[:40])
    return found


def test_only_connectors_imports_drivers_or_opens_engines() -> None:
    files = _files_outside_connectors()
    assert len(files) > 20
    problems = {
        str(path.relative_to(ROOT)): uses
        for path in files
        if (uses := driver_uses(path.read_text("utf-8")))
    }
    assert problems == {}


def test_modules_working_with_external_data_write_no_sql() -> None:
    files = _external_data_files()
    assert any(path.parent.name == "query" for path in files)
    problems = {
        str(path.relative_to(ROOT)): uses
        for path in files
        if (uses := sql_text_uses(path.read_text("utf-8")))
    }
    assert problems == {}


@pytest.mark.parametrize(
    "source",
    [
        "import psycopg",
        "from psycopg import sql",
        "import asyncpg.pool",
        "from sqlalchemy.ext.asyncio import create_async_engine",
        "from sqlalchemy import create_engine",
        "import sqlalchemy\nsqlalchemy.create_engine('x')",
        "conn.exec_driver_sql('x')",
    ],
)
def test_the_driver_scan_finds_drivers_and_engines(source: str) -> None:
    assert driver_uses(source)


@pytest.mark.parametrize(
    "source",
    [
        "from sqlalchemy import text",
        "from sqlalchemy.sql import literal_column",
        "q = 'SELECT heat_no FROM mes.heat'",
        "def f():\n    x = 1\n    return f'delete from {x}'",
        "s = '''update mes.heat\n set a = 1'''",
    ],
)
def test_the_sql_scan_finds_sql_text(source: str) -> None:
    assert sql_text_uses(source)


def test_the_sql_scan_ignores_docstrings_and_prose() -> None:
    source = '"""Select the rows from the bound table."""\nlabel = "选择表"\n'
    assert sql_text_uses(source) == []
