"""Modules hand each other plain data, never ORM objects (AGENTS.md: AI writes only change sets).

An ORM instance handed to another module stays attached to the caller's session: assigning to
it would write to this module's tables on the next commit, a path around the review flow.
"""

import ast
import importlib
import inspect
import typing
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.db import Base
from ontology_platform.modules.documents import service as documents
from ontology_platform.modules.documents.models import Chunk, Document
from ontology_platform.modules.ontology import service as ontology
from test_ontology_support import add_elements, add_ontology, element

PACKAGE = "ontology_platform.modules"
ROOT = Path(importlib.import_module(PACKAGE).__path__[0])


def _module_of(dotted: str) -> str | None:
    """`documents` for `ontology_platform.modules.documents.service`."""
    if not dotted.startswith(PACKAGE + "."):
        return None
    return dotted.removeprefix(PACKAGE + ".").split(".")[0]


def _cross_module_uses(path: Path) -> Iterator[tuple[str, str, int]]:
    """(other module's dotted submodule, attribute used, line) for each use in `path`."""
    own = path.relative_to(ROOT).parts[0]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            other = _module_of(node.module)
            if other is None or other == own:
                continue
            for name in node.names:
                if node.module == f"{PACKAGE}.{other}":
                    # `from …modules.ontology import service as ontology`
                    aliases[name.asname or name.name] = f"{node.module}.{name.name}"
                else:
                    yield node.module, name.name, node.lineno
        elif isinstance(node, ast.Import):
            for name in node.names:
                other = _module_of(name.name)
                if other is not None and other != own:
                    yield name.name, "*", node.lineno
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        ):
            yield aliases[node.value.id], node.attr, node.lineno


def _orm_types(annotation: Any) -> Iterator[type]:
    if inspect.isclass(annotation) and issubclass(annotation, Base):
        yield annotation
    for arg in typing.get_args(annotation):
        yield from _orm_types(arg)


def _problem(dotted: str, attribute: str) -> str | None:
    if attribute == "*":
        return "imports another module whole" if dotted.endswith(".models") else None
    # Enums and constants from another module's models (like identity's Role) are plain data.
    target: ModuleType = importlib.import_module(dotted)
    value = getattr(target, attribute, None)
    if inspect.isclass(value) and issubclass(value, Base):
        return "uses another module's ORM class"
    if inspect.isfunction(value):
        returned = typing.get_type_hints(value).get("return")
        found = list(_orm_types(returned))
        if found:
            return f"receives ORM objects ({', '.join(t.__name__ for t in found)})"
    return None


def test_modules_do_not_exchange_orm_objects() -> None:
    problems = [
        f"{path.relative_to(ROOT)}:{line}: {dotted}.{attribute} {problem}"
        for path in sorted(ROOT.rglob("*.py"))
        for dotted, attribute, line in _cross_module_uses(path)
        if (problem := _problem(dotted, attribute)) is not None
    ]
    assert problems == []


async def test_documents_hands_out_frozen_copies(db: AsyncSession) -> None:
    document = Document(
        id=uuid4(),
        ontology_id=uuid4(),
        filename="a.md",
        media_type="text/markdown",
        size_bytes=1,
        sha256="1" * 64,
        storage_key="k",
        status="extracting",
        progress={"step": "parse", "done": 1, "total": 1},
        uploaded_by=uuid4(),
    )
    db.add(document)
    await db.flush()
    db.add(Chunk(document_id=document.id, seq=0, text="炉次", char_count=2))
    await db.flush()

    info = await documents.get(db, document.id)
    locked = await documents.lock(db, document.id)
    [chunk] = await documents.list_chunks(db, document.id)

    assert not isinstance(info, Base)
    assert not isinstance(locked, Base)
    assert not isinstance(chunk, Base)
    assert (info.filename, locked.status, chunk.text) == ("a.md", "extracting", "炉次")
    with pytest.raises(ValidationError):
        info.change_set_id = uuid4()
    with pytest.raises(ValidationError):
        chunk.text = "x"


async def test_alignment_elements_are_frozen_copies(db: AsyncSession) -> None:
    steel = await add_ontology(db)
    await add_elements(db, element(steel, "entity_type", "Slab", "板坯"))

    [slab] = await ontology.list_alignment_elements(db, steel.id)

    assert not isinstance(slab, Base)
    with pytest.raises(ValidationError):
        slab.label_zh = "钢卷"
    assert await ontology.ontology_exists(db, steel.id)
    assert not await ontology.ontology_exists(db, uuid4())
