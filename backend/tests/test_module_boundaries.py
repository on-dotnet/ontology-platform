"""Modules hand each other plain data, never ORM objects (AGENTS.md: AI writes only change sets).

An ORM instance handed to another module stays attached to the caller's session: assigning to
it would write to this module's tables on the next commit, a path around the review flow.

Only `modules/` is scanned. `main.py` and `worker.py` assemble the modules and may call them
however they need to.
"""

import ast
import dataclasses
import importlib
import importlib.util
import inspect
import typing
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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


def _chain(node: ast.expr) -> list[str] | None:
    """`["a", "b", "c"]` for the expression `a.b.c`."""
    names: list[str] = []
    while isinstance(node, ast.Attribute):
        names.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    names.append(node.id)
    return names[::-1]


def cross_module_uses(
    source: str, dotted_file: str, *, is_package: bool = False
) -> Iterator[tuple[str, int]]:
    """Dotted names from other modules that the file `dotted_file` uses, with their lines.

    Names bound by an import resolve to what they import; attribute chains on them
    (`documents.service.get_row`) are followed to the end.
    """
    own = _module_of(dotted_file)
    package = dotted_file if is_package else dotted_file.rpartition(".")[0]
    tree = ast.parse(source)
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = importlib.util.resolve_name("." * node.level + base, package)
            for name in node.names:
                bound[name.asname or name.name] = f"{base}.{name.name}"
        elif isinstance(node, ast.Import):
            for name in node.names:
                if name.asname:
                    bound[name.asname] = name.name
                else:
                    top = name.name.split(".")[0]
                    bound[top] = top
    targets: set[tuple[str, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Attribute, ast.Name)) and not isinstance(
            getattr(node, "ctx", None), ast.Store
        ):
            chain = _chain(node)
            if chain and chain[0] in bound:
                targets.add((".".join([bound[chain[0]], *chain[1:]]), node.lineno))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for name in node.names:
                targets.add((bound[name.asname or name.name], node.lineno))
    for dotted, line in sorted(targets):
        other = _module_of(dotted)
        if other is not None and other != own:
            yield dotted, line


def _resolve(dotted: str) -> Any:
    """The object a dotted name refers to: the longest importable module, then attributes."""
    parts = dotted.split(".")
    for split in range(len(parts), 0, -1):
        try:
            value: Any = importlib.import_module(".".join(parts[:split]))
        except ModuleNotFoundError:
            continue
        for attribute in parts[split:]:
            value = getattr(value, attribute)
        return value
    raise ModuleNotFoundError(dotted)


def orm_types(annotation: Any, seen: set[int] | None = None) -> Iterator[type]:
    """ORM classes reachable from a type: generic arguments, aliases, dataclass and model fields."""
    seen = set() if seen is None else seen
    if id(annotation) in seen:
        return
    seen.add(id(annotation))
    if isinstance(annotation, typing.TypeAliasType):
        yield from orm_types(annotation.__value__, seen)
        return
    if inspect.isclass(annotation):
        if issubclass(annotation, Base):
            yield annotation
            return
        if dataclasses.is_dataclass(annotation) or issubclass(annotation, BaseModel):
            for hint in typing.get_type_hints(annotation).values():
                yield from orm_types(hint, seen)
    for arg in typing.get_args(annotation):
        yield from orm_types(arg, seen)


def problem(value: Any) -> str | None:
    found = (
        orm_types(typing.get_type_hints(value).get("return"))
        if inspect.isfunction(value)
        else orm_types(value)
    )
    names = sorted({cls.__name__ for cls in found})
    return f"hands out ORM objects ({', '.join(names)})" if names else None


def _dotted_file(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    parts = relative.parts[:-1] if relative.name == "__init__" else relative.parts
    return ".".join([PACKAGE, *parts])


def test_modules_do_not_exchange_orm_objects() -> None:
    files = sorted(ROOT.rglob("*.py"))
    assert len(files) > 20  # the scan really sees the modules
    problems = [
        f"{path.relative_to(ROOT)}:{line}: {dotted} {found}"
        for path in files
        for dotted, line in cross_module_uses(
            path.read_text("utf-8"), _dotted_file(path), is_package=path.name == "__init__.py"
        )
        if (found := problem(_resolve(dotted))) is not None
    ]
    assert problems == []


@pytest.mark.parametrize(
    "source",
    [
        "from ontology_platform.modules.documents.service import get_row",
        "from ontology_platform.modules.documents.models import Document",
        "from ontology_platform.modules.documents import service\nservice.get_row",
        "import ontology_platform.modules.documents.service as docs\ndocs.get_row",
        "import ontology_platform.modules.documents.models as m\nm.Chunk",
        "from ontology_platform.modules import documents\ndocuments.service.get_row",
        "import ontology_platform.modules.documents.service\n"
        "ontology_platform.modules.documents.service.get_row",
        "from ..documents import service\nservice.get_row",
        "from ..documents.models import Document",
    ],
)
def test_the_scan_finds_orm_objects_however_they_are_imported(source: str) -> None:
    found = [
        problem(_resolve(dotted)) for dotted, _ in cross_module_uses(source, f"{PACKAGE}.ai.fake")
    ]
    assert any(found)


def test_the_scan_ignores_the_own_module_and_plain_data() -> None:
    own = "from ontology_platform.modules.documents.service import get_row"
    plain = "from ontology_platform.modules.documents import service\nservice.get"
    assert list(cross_module_uses(own, f"{PACKAGE}.documents.processing")) == []
    found = [problem(_resolve(d)) for d, _ in cross_module_uses(plain, f"{PACKAGE}.ai.fake")]
    assert found
    assert all(item is None for item in found)


@dataclass
class _Holder:
    row: Document


class _Model(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    rows: list[Chunk]


type _Rows = list[Document]


@pytest.mark.parametrize(
    "annotation",
    [Document, list[Document], Document | None, _Holder, _Model, _Rows, Annotated[Chunk, "dep"]],
)
def test_orm_types_are_found_inside_other_types(annotation: Any) -> None:
    assert problem(annotation) is not None


async def test_documents_hands_out_frozen_copies(db: AsyncSession) -> None:
    document = await _document(db)

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
        locked.status = "ready"
    with pytest.raises(ValidationError):
        chunk.text = "x"


async def test_lock_still_locks_the_row(app: FastAPI, db: AsyncSession) -> None:
    document = await _document(db)
    await db.commit()
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    async with factory.begin() as holder:
        await documents.lock(holder, document.id)
        async with factory.begin() as other:
            with pytest.raises(DBAPIError, match="could not obtain lock"):
                await other.execute(
                    select(Document).where(Document.id == document.id).with_for_update(nowait=True)
                )


async def test_alignment_elements_are_frozen_copies(db: AsyncSession) -> None:
    steel = await add_ontology(db)
    await add_elements(db, element(steel, "entity_type", "Slab", "板坯"))

    [slab] = await ontology.list_alignment_elements(db, steel.id)

    assert not isinstance(slab, Base)
    with pytest.raises(ValidationError):
        slab.label_zh = "钢卷"
    assert await ontology.ontology_exists(db, steel.id)
    assert not await ontology.ontology_exists(db, uuid4())


async def _document(db: AsyncSession) -> Document:
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
    return document
